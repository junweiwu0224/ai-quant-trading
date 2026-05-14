# E2E Browser Smoke Tests

This directory contains Playwright smoke tests for the dashboard V2.1 browser flows.

## Prerequisites

The dashboard must be running before executing these tests:

```bash
cd /home/ubuntu/quant-trading-system
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-qlib
```

Install the Node test dependency once:

```bash
npm install
```

## Run

Preferred, reproducible Docker runner:

```bash
npm run e2e:docker
```

Equivalent explicit command:

```bash
docker run --rm --network host \
  -v /home/ubuntu/quant-trading-system:/work \
  -w /work \
  mcr.microsoft.com/playwright:v1.60.0-jammy \
  bash -lc 'PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 npm run e2e'
```

Local runner:

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 \
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/non-snap/chrome-or-chromium \
npm run e2e
```

`PLAYWRIGHT_CHROMIUM_EXECUTABLE` can point to any non-Snap Chrome/Chromium binary. When it is not set, Playwright uses its default browser resolution.

## Current host note

On the current Ubuntu 26.04 host, Playwright's browser download reports unsupported platform and the Snap Chromium crashes under headless automation. If these tests fail with `Target page, context or browser has been closed`, use a non-Snap Chrome/Chromium binary or run the tests in an official Playwright Docker image.
