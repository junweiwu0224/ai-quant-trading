#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${PLAYWRIGHT_BASE_URL:-http://127.0.0.1:8001}"
BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
NODE_BIN="${NODE_BIN:-/Applications/Codex.app/Contents/Resources/node}"
NPM_CLI="$ROOT_DIR/.tools/npm/bin/npm-cli.js"
MODE="${1:-all}"

if [[ ! -x "$NODE_BIN" ]]; then
  echo "Node binary is not available at: $NODE_BIN" >&2
  exit 1
fi

if [[ ! -f "$NPM_CLI" ]]; then
  echo "Local npm CLI is missing at: $NPM_CLI" >&2
  echo "Install the local Node/Playwright toolchain before running this script." >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/.tools/playwright/node_modules/@playwright/test" ]]; then
  echo "Local @playwright/test is missing under .tools/playwright." >&2
  exit 1
fi

if ! curl -fsS --max-time 5 "$BASE_URL" >/dev/null; then
  echo "Dashboard is not reachable at $BASE_URL" >&2
  echo "Start it first, for example:" >&2
  echo "  cd $ROOT_DIR && .venv/bin/python scripts/run_dashboard.py --port 8001 --no-qlib" >&2
  exit 1
fi

export PLAYWRIGHT_BASE_URL="$BASE_URL"
export PLAYWRIGHT_BROWSERS_PATH="$BROWSERS_PATH"
export PLAYWRIGHT_INVITE_CODE="${PLAYWRIGHT_INVITE_CODE:-LOCAL1}"
export PATH="$ROOT_DIR/.tools/node-bin:$ROOT_DIR/.tools/playwright/node_modules/.bin:$PATH"

case "$MODE" in
  all)
    "$NODE_BIN" "$NPM_CLI" run e2e:data-health
    "$NODE_BIN" "$NPM_CLI" run e2e
    ;;
  smoke)
    "$NODE_BIN" "$NPM_CLI" run e2e
    ;;
  data-health)
    "$NODE_BIN" "$NPM_CLI" run e2e:data-health
    ;;
  *)
    echo "Usage: scripts/e2e-local.sh [all|smoke|data-health]" >&2
    exit 2
    ;;
esac
