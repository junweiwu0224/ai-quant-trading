#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${PLAYWRIGHT_BASE_URL:-http://127.0.0.1:8001}"
IMAGE="${PLAYWRIGHT_DOCKER_IMAGE:-mcr.microsoft.com/playwright:v1.60.0-jammy}"

if ! curl -fsS --max-time 5 "$BASE_URL" >/dev/null; then
  echo "Dashboard is not reachable at $BASE_URL" >&2
  echo "Start it first, for example:" >&2
  echo "  cd $ROOT_DIR && .venv/bin/python scripts/run_dashboard.py --port 8001 --no-qlib" >&2
  exit 1
fi

docker run --rm --network host \
  -v "$ROOT_DIR:/work" \
  -w /work \
  "$IMAGE" \
  bash -lc "PLAYWRIGHT_BASE_URL='$BASE_URL' npm run e2e"
