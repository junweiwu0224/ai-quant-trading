const { test, expect } = require('@playwright/test');

const TEST_STOCK_CODE = '600519';

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

test('V2.1 shell loads and command palette opens', async ({ page }) => {
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

    expect(response && response.ok()).toBeTruthy();
});

test('V2.1 stock action contracts are invokable without writes', async ({ page }) => {
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

test('V2.1 right rail offcanvas switches stock context without lifecycle residue', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    const result = await page.evaluate(async () => {
        const firstCode = '600519';
        const secondCode = '000001';

        await window.App.openOffcanvas(firstCode);
        await window.PanelLifecycle.syncWithRail({ source: 'playwright:first-open' });
        const firstRail = window.RightRailController.getState();
        const firstLifecycle = window.PanelLifecycle.getState();
        const firstStore = window.GlobalStockStore.getState();
        const firstPanel = document.getElementById('stock-offcanvas');
        const firstDomActive = firstPanel && firstPanel.classList.contains('active');
        const firstAriaHidden = firstPanel && firstPanel.getAttribute('aria-hidden');

        await window.App.openOffcanvas(secondCode);
        await window.PanelLifecycle.syncWithRail({ source: 'playwright:second-open' });
        const secondRail = window.RightRailController.getState();
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
    expect(result.closed.lifecycleMounted).toBe('stock-offcanvas');
    expect(result.closed.lifecycleInstanceActive).toBeFalsy();
    expect(result.closed.domActive).toBeFalsy();
    expect(result.closed.ariaHidden).toBe('true');
});
