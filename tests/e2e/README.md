# E2E Browser Smoke Tests

This directory contains Playwright smoke tests for the dashboard V2.1 browser flows.

## Prerequisites

The dashboard must be running before executing these tests:

```bash
cd /path/to/ai-quant-trading
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service
```

The local runner resolves the workspace Node/Playwright toolchain from `.tools/`
or `node_modules`; no Docker or production service is started by the script.

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
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh smoke
```

Pass extra Playwright arguments after the mode, for example:

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh smoke --grep "stock hash restores"
```
