from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/e2e-local.sh"
E2E_README = ROOT / "tests/e2e/README.md"


def test_e2e_local_script_has_valid_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_e2e_local_script_resolves_node_and_playwright_cli_flexibly():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "resolve_node_bin()" in text
    assert "command -v node" in text
    assert "find_playwright_cli()" in text
    assert ".test-*/cli.js" in text
    assert "PLAYWRIGHT_NODE_PATH_TMP" in text
    assert 'trap \'rm -rf "$tmp_node_path"\'' not in text
    assert 'playwright.config.cjs' in text
    assert "npm run e2e" not in text


def test_e2e_readme_uses_portable_workspace_path():
    text = E2E_README.read_text(encoding="utf-8")

    assert "/Users/junwei/" not in text
    assert "cd /path/to/ai-quant-trading" in text
