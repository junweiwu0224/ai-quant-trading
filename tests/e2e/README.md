# Vue E2E Browser Smoke Tests

This directory contains Playwright smoke tests for the Vue-only dashboard. The route matrix
replaces the retired Jinja/Vanilla V2.1 shell tests while keeping their user-visible coverage:
desktop/mobile navigation, stock research, validation, reports, simulated trading, AI/Agent
workflows, responsive overflow, bad-value detection, and deterministic safety boundaries.

## Prerequisites

The dashboard must be running before executing these tests:

```bash
cd /home/ubuntu/quant-trading-system
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service
```

Install the Node test dependency once:

```bash
npm install
```

## Run

Local runner on this macOS workspace:

```bash
scripts/e2e-local.sh all
```

Targeted local runs:

```bash
scripts/e2e-local.sh smoke
scripts/e2e-local.sh data-health
```

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

`npm run e2e`, `npm run e2e:vue` and `npm run e2e:data-health` only run current Vue flows.
The old `v2-smoke.spec.cjs` and `data-display-health.spec.cjs` fixtures were retired after
their coverage was mapped to `vue-migration.spec.cjs` and `vue-workspace-health.spec.cjs`;
they depended on the deleted `window.App`, offcanvas and Vanilla panel lifecycle.
