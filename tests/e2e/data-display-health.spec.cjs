const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const TEST_STOCK_CODE = '600519';
const TEST_INVITE_CODE = process.env.PLAYWRIGHT_INVITE_CODE || 'LOCAL1';
const TEST_PASSWORD = 'Playwright123!';
const REPORT_DIR = path.join(process.cwd(), 'test-results', 'data-display-audit');
const REPORT_PATH = path.join(REPORT_DIR, 'browser-report.json');
const DEFAULT_BASE_URL = 'http://127.0.0.1:8001';
const HARD_BAD_TEXT = /(?:\b(?:NaN|undefined|Infinity)\b|\[object Object\]|\bInvalid Date\b)/gi;
const TAB_WAIT_MS = 3000;
const STOCK_WAIT_MS = 5000;

const TAB_AUDITS = [
    { tab: 'overview', panelId: 'tab-overview' },
    { tab: 'intelligence', panelId: 'tab-intelligence' },
    { tab: 'research', panelId: 'tab-research' },
    { tab: 'trade', panelId: 'tab-trade' },
    { tab: 'paper', panelId: 'tab-paper' },
    { tab: 'strategy-admin', panelId: 'tab-strategy' },
];

function getBaseUrl() {
    return process.env.PLAYWRIGHT_BASE_URL || DEFAULT_BASE_URL;
}

function getCookieDomain() {
    try {
        return new URL(getBaseUrl()).hostname || '127.0.0.1';
    } catch {
        return '127.0.0.1';
    }
}

function serializeError(error) {
    if (!error) return null;
    return {
        name: error.name || 'Error',
        message: error.message || String(error),
        stack: error.stack || '',
    };
}

function extractSessionCookie(response) {
    const sessionCookie = response.headers()['set-cookie'] || '';
    return sessionCookie.match(/quant_session=([^;]+)/)?.[1] || '';
}

async function setSessionCookie(page, cookieValue) {
    if (!cookieValue) {
        throw new Error('Authentication succeeded without a quant_session cookie');
    }
    await page.context().addCookies([{
        name: 'quant_session',
        value: cookieValue,
        domain: getCookieDomain(),
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
    }]);
}

async function ensureAuthenticated(page, usernameSuffix = Date.now()) {
    const username = `audit_${usernameSuffix}`.replace(/[^A-Za-z0-9_.-]/g, '').slice(0, 32);
    const payload = {
        username,
        password: TEST_PASSWORD,
        invite_code: TEST_INVITE_CODE,
        display_name: username,
        email: null,
    };

    const auth = await page.request.post('/api/account/register', { data: payload });
    if (auth.ok()) {
        await setSessionCookie(page, extractSessionCookie(auth));
        return { mode: 'register', username, registerStatus: auth.status() };
    }

    const fallbackLogins = [
        { username, password: TEST_PASSWORD },
        { username: 'pw_shell', password: TEST_PASSWORD },
    ];
    const loginStatuses = [];
    for (const credentials of fallbackLogins) {
        const login = await page.request.post('/api/account/login', { data: credentials });
        loginStatuses.push({ username: credentials.username, status: login.status(), ok: login.ok() });
        if (login.ok()) {
            await setSessionCookie(page, extractSessionCookie(login));
            return {
                mode: 'login',
                username: credentials.username,
                registerStatus: auth.status(),
                loginStatuses,
            };
        }
    }

    throw new Error(`Authentication failed: register status ${auth.status()}, login statuses ${JSON.stringify(loginStatuses)}`);
}

async function waitForAppReady(page) {
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('#stock-offcanvas')).toBeAttached();
    await page.waitForFunction(() => {
        return Boolean(
            window.App
            && typeof window.App.switchTab === 'function'
            && (window.APIClient || window.BusinessAdapter)
        );
    }, null, { timeout: 20_000 });
}

function findHardMatches(text) {
    HARD_BAD_TEXT.lastIndex = 0;
    return [...new Set(String(text || '').match(HARD_BAD_TEXT) || [])].slice(0, 20);
}

function countPlaceholders(text) {
    return (String(text || '').match(/--/g) || []).length;
}

async function switchToTab(page, tabName) {
    const result = { requested: tabName, fallbackClick: false };
    try {
        await page.evaluate(async (name) => {
            if (!window.App || typeof window.App.switchTab !== 'function') {
                throw new Error('window.App.switchTab is not available');
            }
            await window.App.switchTab(name);
        }, tabName);
        return result;
    } catch (error) {
        result.switchError = serializeError(error);
    }

    try {
        const nav = page.locator(`.nav-link[data-tab="${tabName}"]`).first();
        if (await nav.count()) {
            await nav.click();
            result.fallbackClick = true;
        }
    } catch (error) {
        result.fallbackClickError = serializeError(error);
    }
    return result;
}

async function readPanelState(page, panelId) {
    return page.evaluate((id) => {
        const panel = document.getElementById(id);
        if (!panel) {
            return {
                panelId: id,
                exists: false,
                visible: false,
                active: false,
                hidden: false,
                ariaHidden: null,
                className: '',
                text: '',
            };
        }
        const style = getComputedStyle(panel);
        const hidden = panel.hasAttribute('hidden');
        const ariaHidden = panel.getAttribute('aria-hidden');
        const visible = !hidden
            && ariaHidden !== 'true'
            && style.display !== 'none'
            && style.visibility !== 'hidden';
        return {
            panelId: id,
            exists: true,
            visible,
            active: panel.classList.contains('active'),
            hidden,
            ariaHidden,
            className: panel.className,
            text: panel.innerText || '',
        };
    }, panelId);
}

async function collectPanelSnapshot(page, audit) {
    const switchResult = await switchToTab(page, audit.tab);
    await page.waitForFunction((panelId) => {
        const panel = document.getElementById(panelId);
        return Boolean(panel && !panel.hasAttribute('hidden') && getComputedStyle(panel).display !== 'none');
    }, audit.panelId, { timeout: TAB_WAIT_MS }).catch(() => {});
    await page.waitForTimeout(250);

    try {
        const state = await readPanelState(page, audit.panelId);
        const text = state.text || '';
        delete state.text;
        return {
            tab: audit.tab,
            ...state,
            textLength: text.length,
            hardMatches: findHardMatches(text),
            placeholderCount: countPlaceholders(text),
            switchResult,
        };
    } catch (error) {
        return {
            tab: audit.tab,
            panelId: audit.panelId,
            exists: false,
            visible: false,
            active: false,
            textLength: 0,
            hardMatches: [],
            placeholderCount: 0,
            switchResult,
            captureError: serializeError(error),
        };
    }
}

async function collectStockDetailSnapshot(page, code) {
    let openError = null;
    try {
        await page.evaluate(async (stockCode) => {
            if (!window.App || typeof window.App.openStockDetail !== 'function') {
                throw new Error('window.App.openStockDetail is not available');
            }
            await window.App.openStockDetail(stockCode, {
                source: 'playwright:data-display-health',
                preferDirectOpen: true,
            });
        }, code);
    } catch (error) {
        openError = serializeError(error);
    }

    await page.waitForFunction(() => {
        const panel = document.getElementById('tab-stock');
        return Boolean(panel && !panel.hasAttribute('hidden') && getComputedStyle(panel).display !== 'none');
    }, null, { timeout: STOCK_WAIT_MS }).catch(() => {});
    await page.waitForFunction((stockCode) => {
        const headerCode = document.getElementById('sd-code')?.innerText || '';
        const inputCode = document.getElementById('stock-detail-code')?.value || '';
        return headerCode.includes(stockCode) || inputCode.includes(stockCode);
    }, code, { timeout: STOCK_WAIT_MS }).catch(() => {});
    await page.waitForTimeout(500);

    try {
        const state = await readPanelState(page, 'tab-stock');
        const text = state.text || '';
        delete state.text;
        return {
            code,
            ...state,
            displayedCode: await page.locator('#sd-code').innerText({ timeout: 1000 }).catch(() => ''),
            textLength: text.length,
            hardMatches: findHardMatches(text),
            placeholderCount: countPlaceholders(text),
            openError,
        };
    } catch (error) {
        return {
            code,
            panelId: 'tab-stock',
            exists: false,
            visible: false,
            active: false,
            displayedCode: '',
            textLength: 0,
            hardMatches: [],
            placeholderCount: 0,
            openError,
            captureError: serializeError(error),
        };
    }
}

function collectHardFindings(panels, stockDetail) {
    return [
        ...panels.flatMap((panel) => panel.hardMatches.map((match) => ({
            area: 'panel',
            tab: panel.tab,
            match,
        }))),
        ...stockDetail.hardMatches.map((match) => ({
            area: 'stockDetail',
            code: stockDetail.code,
            match,
        })),
    ];
}

function writeReport(report) {
    fs.mkdirSync(REPORT_DIR, { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), 'utf8');
}

test('dashboard data display health audit', async ({ page }) => {
    const report = {
        generatedAt: new Date().toISOString(),
        baseUrl: getBaseUrl(),
        url: '',
        auth: null,
        initialResponse: null,
        consoleErrors: [],
        failedRequests: [],
        panels: [],
        stockDetail: {
            code: TEST_STOCK_CODE,
            panelId: 'tab-stock',
            exists: false,
            visible: false,
            active: false,
            displayedCode: '',
            textLength: 0,
            hardMatches: [],
            placeholderCount: 0,
            openError: null,
        },
        hardFindings: [],
        runError: null,
    };

    page.on('console', (message) => {
        if (['error', 'warning'].includes(message.type())) {
            report.consoleErrors.push({
                type: message.type(),
                text: message.text(),
                location: message.location(),
            });
        }
    });
    page.on('requestfailed', (request) => {
        report.failedRequests.push({
            url: request.url(),
            method: request.method(),
            resourceType: request.resourceType(),
            failure: request.failure() ? request.failure().errorText : '',
        });
    });

    try {
        report.auth = await ensureAuthenticated(page, 'data_display');
        const response = await page.goto('/', { waitUntil: 'domcontentloaded' });
        report.initialResponse = response
            ? { url: response.url(), status: response.status(), ok: response.ok() }
            : null;
        await waitForAppReady(page);

        for (const audit of TAB_AUDITS) {
            report.panels.push(await collectPanelSnapshot(page, audit));
        }
        report.stockDetail = await collectStockDetailSnapshot(page, TEST_STOCK_CODE);
        report.url = page.url();
        report.hardFindings = collectHardFindings(report.panels, report.stockDetail);
    } catch (error) {
        report.url = page.url();
        report.runError = serializeError(error);
    } finally {
        writeReport(report);
    }

    expect(report.runError, JSON.stringify(report, null, 2)).toBeNull();
    expect(report.panels.length, JSON.stringify(report, null, 2)).toBe(TAB_AUDITS.length);
    expect(report.panels.filter((panel) => !panel.exists || !panel.visible), JSON.stringify(report, null, 2)).toEqual([]);
    expect(report.stockDetail.exists, JSON.stringify(report, null, 2)).toBeTruthy();
    expect(report.stockDetail.visible, JSON.stringify(report, null, 2)).toBeTruthy();
    const hardPanelMatches = report.panels.flatMap((panel) => (
        panel.hardMatches.map((match) => `${panel.tab}:${match}`)
    ));
    expect(hardPanelMatches, JSON.stringify(report, null, 2)).toEqual([]);
    expect(report.stockDetail.hardMatches, JSON.stringify(report, null, 2)).toEqual([]);
});
