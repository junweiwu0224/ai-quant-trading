const path = require('path');

const dashboardBaseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8001';
const browserExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;

module.exports = {
    testDir: path.join(__dirname, 'tests/e2e'),
    timeout: 60_000,
    expect: {
        timeout: 10_000,
    },
    use: {
        baseURL: dashboardBaseUrl,
        headless: true,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        launchOptions: {
            ...(browserExecutable ? { executablePath: browserExecutable } : {}),
            args: [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-crash-reporter',
            ],
        },
    },
    reporter: [['line']],
};
