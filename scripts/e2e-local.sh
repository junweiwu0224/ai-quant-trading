#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${PLAYWRIGHT_BASE_URL:-http://127.0.0.1:8001}"
BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
MODE="${1:-all}"
shift || true
PLAYWRIGHT_NODE_PATH_TMP=""

resolve_node_bin() {
  if [[ -n "${NODE_BIN:-}" && -x "$NODE_BIN" ]]; then
    echo "$NODE_BIN"
    return 0
  fi
  if command -v node >/dev/null 2>&1; then
    command -v node
    return 0
  fi
  local runtime_node="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
  if [[ -x "$runtime_node" ]]; then
    echo "$runtime_node"
    return 0
  fi
  local repo_node="$ROOT_DIR/.tools/node-bin/node"
  if [[ -x "$repo_node" ]]; then
    echo "$repo_node"
    return 0
  fi
  return 1
}

find_playwright_cli() {
  local direct="$ROOT_DIR/.tools/playwright/node_modules/@playwright/test/cli.js"
  if [[ -f "$direct" ]]; then
    echo "$direct"
    return 0
  fi
  local hidden
  hidden="$(find "$ROOT_DIR/.tools/playwright/node_modules/@playwright" -maxdepth 2 -path '*/.test-*/cli.js' -type f 2>/dev/null | head -n 1 || true)"
  if [[ -n "$hidden" && -f "$hidden" ]]; then
    echo "$hidden"
    return 0
  fi
  local package_cli="$ROOT_DIR/node_modules/@playwright/test/cli.js"
  if [[ -f "$package_cli" ]]; then
    echo "$package_cli"
    return 0
  fi
  return 1
}

find_playwright_test_dir() {
  local direct="$ROOT_DIR/.tools/playwright/node_modules/@playwright/test"
  if [[ -d "$direct" ]]; then
    echo "$direct"
    return 0
  fi
  local hidden
  hidden="$(find "$ROOT_DIR/.tools/playwright/node_modules/@playwright" -maxdepth 1 -path '*/.test-*' -type d 2>/dev/null | head -n 1 || true)"
  if [[ -n "$hidden" && -d "$hidden" ]]; then
    echo "$hidden"
    return 0
  fi
  local package_dir="$ROOT_DIR/node_modules/@playwright/test"
  if [[ -d "$package_dir" ]]; then
    echo "$package_dir"
    return 0
  fi
  return 1
}

prepare_playwright_node_path() {
  local package_dir="$1"
  if [[ "$package_dir" == */node_modules/@playwright/test ]]; then
    return 0
  fi
  PLAYWRIGHT_NODE_PATH_TMP="$(mktemp -d "${TMPDIR:-/tmp}/aiqt-playwright-node-path.XXXXXX")"
  mkdir -p "$PLAYWRIGHT_NODE_PATH_TMP/@playwright"
  ln -s "$package_dir" "$PLAYWRIGHT_NODE_PATH_TMP/@playwright/test"
  export NODE_PATH="$PLAYWRIGHT_NODE_PATH_TMP${NODE_PATH:+:$NODE_PATH}"
  trap cleanup_playwright_node_path EXIT
}

cleanup_playwright_node_path() {
  if [[ -n "${PLAYWRIGHT_NODE_PATH_TMP:-}" ]]; then
    rm -rf "$PLAYWRIGHT_NODE_PATH_TMP"
  fi
}

NODE_BIN="$(resolve_node_bin || true)"
if [[ -z "$NODE_BIN" ]]; then
  echo "Node binary is not available. Set NODE_BIN or install node." >&2
  exit 1
fi

PLAYWRIGHT_CLI="$(find_playwright_cli || true)"
if [[ -z "$PLAYWRIGHT_CLI" ]]; then
  echo "Local Playwright CLI is missing under .tools/playwright or node_modules." >&2
  echo "Install the local Node/Playwright toolchain before running this script." >&2
  exit 1
fi

PLAYWRIGHT_TEST_DIR="$(find_playwright_test_dir || true)"
if [[ -z "$PLAYWRIGHT_TEST_DIR" ]]; then
  echo "Local @playwright/test package is missing under .tools/playwright or node_modules." >&2
  exit 1
fi
prepare_playwright_node_path "$PLAYWRIGHT_TEST_DIR"

if ! curl -fsS --max-time 5 "$BASE_URL" >/dev/null; then
  echo "Dashboard is not reachable at $BASE_URL" >&2
  echo "Start it first, for example:" >&2
  echo "  cd $ROOT_DIR && .venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service" >&2
  exit 1
fi

export PLAYWRIGHT_BASE_URL="$BASE_URL"
export PLAYWRIGHT_BROWSERS_PATH="$BROWSERS_PATH"
export PLAYWRIGHT_INVITE_CODE="${PLAYWRIGHT_INVITE_CODE:-LOCAL1}"
export PATH="$ROOT_DIR/.tools/node-bin:$ROOT_DIR/.tools/playwright/node_modules/.bin:$ROOT_DIR/node_modules/.bin:$PATH"

run_playwright() {
  "$NODE_BIN" "$PLAYWRIGHT_CLI" test --config=playwright.config.cjs "$@"
}

case "$MODE" in
  all)
    run_playwright tests/e2e/data-display-health.spec.cjs "$@"
    run_playwright tests/e2e/v2-smoke.spec.cjs tests/e2e/openclaw.spec.cjs "$@"
    ;;
  smoke)
    run_playwright tests/e2e/v2-smoke.spec.cjs tests/e2e/openclaw.spec.cjs "$@"
    ;;
  data-health)
    run_playwright tests/e2e/data-display-health.spec.cjs "$@"
    ;;
  *)
    echo "Usage: scripts/e2e-local.sh [all|smoke|data-health]" >&2
    exit 2
    ;;
esac
