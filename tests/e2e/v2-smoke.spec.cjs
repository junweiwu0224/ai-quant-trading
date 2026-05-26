const { test, expect } = require('@playwright/test');

const TEST_STOCK_CODE = '600519';
const TEST_INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';
const TEST_PASSWORD = 'Playwright123!';

function getCookieDomain() {
    try {
        const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001';
        return new URL(baseUrl).hostname || '127.0.0.1';
    } catch {
        return '127.0.0.1';
    }
}

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
    const cookieDomain = getCookieDomain();
    const payload = {
        username,
        password: TEST_PASSWORD,
        invite_code: TEST_INVITE_CODE,
        display_name: username,
        email: null,
    };
    const auth = await page.request.post('/api/account/register', { data: payload });
    if (!auth.ok()) {
        const login = await page.request.post('/api/account/login', {
            data: { username: 'pw_shell', password: TEST_PASSWORD },
        });
        expect(login.ok()).toBeTruthy();
        const sessionCookie = login.headers()['set-cookie'] || '';
        await page.context().addCookies([{
            name: 'quant_session',
            value: sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '',
            domain: cookieDomain,
            path: '/',
            httpOnly: true,
            sameSite: 'Lax',
        }]);
        return username;
    }
    const sessionCookie = auth.headers()['set-cookie'] || '';
    await page.context().addCookies([{
        name: 'quant_session',
        value: sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '',
        domain: cookieDomain,
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
    }]);
    return username;
}

test('V2.1 shell loads and command palette opens', async ({ page }) => {
    await ensureAuthenticated(page, 'shell');
    const response = await page.goto('/', { waitUntil: 'domcontentloaded' });

    await waitForAppReady(page);
    await page.evaluate(() => window.CommandPalette.open({ source: 'playwright:v2-shell' }));

    const palette = page.locator('#cmd-palette');
    await expect(palette).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(page.locator('#stock-offcanvas')).toBeAttached();

    const jumpLink = page.locator('[data-app-action="switch-tab"][data-tab="trade"]').first();
    await expect(jumpLink).toBeVisible();
    await jumpLink.click();
    await expect(page.locator('#tab-trade')).toBeVisible();

    await expect(page.locator('#nav-paper')).toHaveAttribute('aria-controls', 'tab-paper');
    await page.evaluate(() => window.App.switchTab('paper'));
    await expect(page.locator('#tab-paper')).toBeVisible();
    await expect(page.locator('#nav-paper')).toHaveClass(/active/);
    await page.evaluate(() => window.App.switchTab('trade'));
    await expect(page.locator('#tab-trade')).toBeVisible();
    await page.evaluate(() => window.App.switchTab('sim'));
    await expect(page.locator('#tab-paper')).toBeVisible();
    await expect(page.locator('#nav-paper')).toHaveClass(/active/);
    await expect(page).toHaveURL(/#paper$/);

    expect(response && response.ok()).toBeTruthy();
});

test('V2.1 stock action contracts are invokable without writes', async ({ page }) => {
    await ensureAuthenticated(page, 'stock_actions');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    const result = await page.evaluate(async (code) => {
        const canAdd = await window.LocalMCP.canInvoke({
            toolId: 'add_to_watchlist',
            input: { code },
            source: 'playwright:v2-actions',
        });
        const canRemove = await window.LocalMCP.canInvoke({
            toolId: 'remove_from_watchlist',
            input: { code },
            source: 'playwright:v2-actions',
        });
        const canOpen = await window.LocalMCP.canInvoke({
            toolId: 'open_stock_detail',
            input: { code },
            source: 'playwright:v2-actions',
        });
        const open = await window.App.openStockDetail(code, {
            source: 'playwright:v2-open',
        });
        const activeStock = window.GlobalStockStore.getState();

        return {
            hasAddAction: window.ActionRegistry.has('add_to_watchlist'),
            hasRemoveAction: window.ActionRegistry.has('remove_from_watchlist'),
            hasOpenAction: window.ActionRegistry.has('open_stock_detail'),
            canAdd,
            canRemove,
            canOpen,
            open,
            activeStockCode: activeStock && activeStock.identity && activeStock.identity.code,
        };
    }, TEST_STOCK_CODE);

    expect(result.hasAddAction).toBeTruthy();
    expect(result.hasRemoveAction).toBeTruthy();
    expect(result.hasOpenAction).toBeTruthy();
    expect(result.canAdd.ok).toBeTruthy();
    expect(result.canRemove.ok).toBeTruthy();
    expect(result.canOpen.ok).toBeTruthy();
    expect(result.open.ok).toBeTruthy();
    expect(result.activeStockCode).toBe(TEST_STOCK_CODE);
});

test('V2.1 stock hash restores a concrete stock detail on refresh', async ({ page }) => {
    await ensureAuthenticated(page, 'stock_refresh');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await page.evaluate(async (code) => {
        await window.App.openStockDetail(code, {
            source: 'playwright:v2-stock-refresh',
            preferDirectOpen: true,
        });
    }, TEST_STOCK_CODE);

    await expect(page).toHaveURL(/#stock$/);
    await expect(page.locator('#sd-code')).toHaveText(TEST_STOCK_CODE);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await expect(page).toHaveURL(/#stock$/);
    await expect(page.locator('#tab-stock')).toBeVisible();
    await expect(page.locator('#sd-code')).toHaveText(TEST_STOCK_CODE);

    const restored = await page.evaluate(() => ({
        currentTab: window.App.currentTab,
        researchContext: window.App.getContext('research'),
        valuationPanel: {
            code: document.getElementById('research-panel-valuation')?.dataset?.activeStockCode || '',
            name: document.getElementById('research-panel-valuation')?.dataset?.activeStockName || '',
        },
        savedCode: window.sessionStorage.getItem('last_stock_code'),
    }));

    expect(restored.currentTab).toBe('stock');
    expect(restored.researchContext?.activeStock?.code || restored.valuationPanel.code).toBe(TEST_STOCK_CODE);
    expect(restored.valuationPanel.code).toBe(TEST_STOCK_CODE);
    expect(restored.savedCode).toBe(TEST_STOCK_CODE);
});

test('V2.1 conditional order section is available without writes', async ({ page }) => {
    await ensureAuthenticated(page, 'orders');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await expect(page.locator('#conditional-order-section')).toBeVisible();
    await expect(page.locator('#cond-alert-rule')).toBeVisible();
    await expect(page.locator('#cond-rules-table')).toBeVisible();
    await expect(page.locator('#cond-events')).toBeVisible();
});

test('V2.1 right rail offcanvas switches stock context without lifecycle residue', async ({ page }) => {
    await ensureAuthenticated(page, 'rail');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    const result = await page.evaluate(async () => {
        const firstCode = '600519';
        const secondCode = '000001';

        async function waitForRailCode(code) {
            for (let attempt = 0; attempt < 20; attempt += 1) {
                const state = window.RightRailController.getState();
                if (state.context && state.context.stock && state.context.stock.code === code) {
                    return state;
                }
                await new Promise((resolve) => window.requestAnimationFrame(resolve));
            }
            return window.RightRailController.getState();
        }

        await window.App.openOffcanvas(firstCode);
        await window.PanelLifecycle.syncWithRail({ source: 'playwright:first-open' });
        const firstRail = await waitForRailCode(firstCode);
        const firstLifecycle = window.PanelLifecycle.getState();
        const firstStore = window.GlobalStockStore.getState();
        const firstPanel = document.getElementById('stock-offcanvas');
        const firstDomActive = firstPanel && firstPanel.classList.contains('active');
        const firstAriaHidden = firstPanel && firstPanel.getAttribute('aria-hidden');

        await window.App.openOffcanvas(secondCode);
        await window.PanelLifecycle.syncWithRail({ source: 'playwright:second-open' });
        const secondRail = await waitForRailCode(secondCode);
        const secondLifecycle = window.PanelLifecycle.getState();
        const secondStore = window.GlobalStockStore.getState();
        const secondPanel = document.getElementById('stock-offcanvas');
        const secondDomActive = secondPanel && secondPanel.classList.contains('active');
        const secondAriaHidden = secondPanel && secondPanel.getAttribute('aria-hidden');

        window.App.closeOffcanvas();
        await window.PanelLifecycle.syncWithRail({ source: 'playwright:close' });
        const closedRail = window.RightRailController.getState();
        const closedLifecycle = window.PanelLifecycle.getState();
        const closedPanel = document.getElementById('stock-offcanvas');
        const closedDomActive = closedPanel && closedPanel.classList.contains('active');
        const closedAriaHidden = closedPanel && closedPanel.getAttribute('aria-hidden');

        return {
            first: {
                railOpen: firstRail.isOpen,
                railPanel: firstRail.activePanelId,
                railCode: firstRail.context && firstRail.context.stock && firstRail.context.stock.code,
                panelParamsCode: firstRail.panelParams && firstRail.panelParams.code,
                lifecycleActive: firstLifecycle.activePanelId,
                lifecycleMounted: firstLifecycle.mountedPanelId,
                storeCode: firstStore.identity && firstStore.identity.code,
                domActive: firstDomActive,
                ariaHidden: firstAriaHidden,
            },
            second: {
                railOpen: secondRail.isOpen,
                railPanel: secondRail.activePanelId,
                railCode: secondRail.context && secondRail.context.stock && secondRail.context.stock.code,
                panelParamsCode: secondRail.panelParams && secondRail.panelParams.code,
                lifecycleActive: secondLifecycle.activePanelId,
                lifecycleMounted: secondLifecycle.mountedPanelId,
                storeCode: secondStore.identity && secondStore.identity.code,
                domActive: secondDomActive,
                ariaHidden: secondAriaHidden,
            },
            closed: {
                railOpen: closedRail.isOpen,
                railPanel: closedRail.activePanelId,
                lifecycleActive: closedLifecycle.activePanelId,
                lifecycleMounted: closedLifecycle.mountedPanelId,
                lifecycleInstanceActive: closedLifecycle.currentInstanceActive,
                domActive: closedDomActive,
                ariaHidden: closedAriaHidden,
            },
        };
    });

    expect(result.first.railOpen).toBeTruthy();
    expect(result.first.railPanel).toBe('stock-offcanvas');
    expect(result.first.railCode).toBe('600519');
    expect(result.first.panelParamsCode).toBe('600519');
    expect(result.first.lifecycleActive).toBe('stock-offcanvas');
    expect(result.first.lifecycleMounted).toBe('stock-offcanvas');
    expect(result.first.storeCode).toBe('600519');
    expect(result.first.domActive).toBeTruthy();
    expect(result.first.ariaHidden).toBe('false');

    expect(result.second.railOpen).toBeTruthy();
    expect(result.second.railPanel).toBe('stock-offcanvas');
    expect(result.second.railCode).toBe('000001');
    expect(result.second.panelParamsCode).toBe('000001');
    expect(result.second.lifecycleActive).toBe('stock-offcanvas');
    expect(result.second.lifecycleMounted).toBe('stock-offcanvas');
    expect(result.second.storeCode).toBe('000001');
    expect(result.second.domActive).toBeTruthy();
    expect(result.second.ariaHidden).toBe('false');

    expect(result.closed.railPanel).toBeNull();
    expect(result.closed.lifecycleActive).toBeNull();
    expect(result.closed.lifecycleMounted).toBeNull();
    expect(result.closed.lifecycleInstanceActive).toBeFalsy();
    expect(result.closed.domActive).toBeFalsy();
    expect(result.closed.ariaHidden).toBe('true');
});

test('A-Stock valuation center surfaces ledger metadata across research and detail views', async ({ page }) => {
    await ensureAuthenticated(page, 'valuation_ledger');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await page.evaluate(() => window.App.switchTab('research'));
    await expect(page.locator('.research-sub-tab[data-subtab="valuation"]')).toBeVisible();
    await page.locator('.research-sub-tab[data-subtab="valuation"]').click();
    await page.waitForFunction(() => Boolean(window.ResearchValuation));
    await page.evaluate(() => {
        globalThis.ResearchValuation?.addCode?.({ code: '600519', name: '贵州茅台' });
    });

    await expect.poll(async () => page.evaluate(() => window.App.getContext('research'))).toMatchObject({
        type: 'research',
        activeSubtab: 'valuation',
        activeStock: { code: TEST_STOCK_CODE },
    });
    await expect(page.locator('#research-panel-valuation')).toHaveAttribute('data-active-stock-code', TEST_STOCK_CODE);
    await expect(page.locator('#valuation-detail')).toContainText('来源', { timeout: 20_000 });

    await page.locator('.research-sub-tab[data-subtab="datahub"]').click();
    await page.waitForFunction(() => Boolean(window.ResearchDataHub));
    await page.evaluate(() => {
        globalThis.ResearchDataHub?._addCode?.({ code: '600519', name: '贵州茅台' });
    });
    await expect(page.locator('#datahub-source-health')).toContainText(/在线|--/);
    await expect(page.locator('#datahub-quality-summary')).toBeVisible();

    await page.evaluate(() => window.App.switchTab('stock'));
    await page.waitForFunction(() => Boolean(window.StockDetail));
    await page.evaluate(async () => {
        await window.App.openStockDetail('600519', { source: 'playwright:valuation-ledger' });
    });
    await expect(page.locator('#sd-valuation-snapshot')).toContainText('估值源');
});
