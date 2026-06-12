#!/usr/bin/env python3
"""Static deployment checks that do not start Docker or external services."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


SECRET_VALUE_RE = re.compile(
    r"\b(?:api[_-]?key|secret|token|password|cookie)\b\s*[:=]\s*(?!\$\{[^}]+:-?\}|['\"]?\s*$)['\"]?([^'\"\s#]+)"
    r"|-\s*[A-Z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|COOKIE)[A-Z0-9_]*=(?!\$\{[^}]+:-?\}|['\"]?\s*$)['\"]?([^'\"\s#]+)",
    re.IGNORECASE,
)
PLACEHOLDER_VALUES = {"", "your-api-key", "bridge-secret", "test", "local1"}
REQUIRED_DECISION_DOCS = {
    "docs/decisions/0004-production-release-risk-gates.md": [
        "OpenClaw",
        "--auth none",
        "18789",
        "iWencai",
        "LLM",
        "paper/live/broker/trading",
    ],
    "docs/release-evidence/production-release-decision-template.md": [
        "OpenClaw Auth And Network Gate",
        "Real Provider / iWencai Gate",
        "OpenClaw / LLM Gate",
        "Data Sync And Migration Gate",
        "Paper / Live / Broker Gate",
    ],
}


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    message: str


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _line_after(text: str, needle: str, *, window: int = 20) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[index : index + window])
    return ""


def _service_block(text: str, service: str) -> str:
    pattern = re.compile(rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)")
    match = pattern.search(text)
    return match.group("body") if match else ""


def _secret_findings(relative: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = SECRET_VALUE_RE.search(line)
        if not match:
            continue
        value = next(group for group in match.groups() if group is not None).strip().strip("'\"")
        if not value or value.lower() in PLACEHOLDER_VALUES:
            continue
        findings.append(
            Finding(
                "hard",
                "secret-values",
                f"{relative}:{line_number} appears to contain a literal secret-like value.",
            )
        )
    return findings


def _decision_doc_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative, required_terms in REQUIRED_DECISION_DOCS.items():
        path = root / relative
        if not path.is_file():
            findings.append(
                Finding(
                    "hard",
                    "release-risk-decision",
                    f"Missing production release risk decision document: {relative}",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        missing_terms = [term for term in required_terms if term not in text]
        if missing_terms:
            findings.append(
                Finding(
                    "hard",
                    "release-risk-decision",
                    f"{relative} does not document required release gates: {', '.join(missing_terms)}",
                )
            )
    return findings


def run_checks(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    required = ["docker-compose.yml", "Dockerfile", ".dockerignore", ".env.example"]
    missing = [relative for relative in required if not (root / relative).is_file()]
    for relative in missing:
        findings.append(Finding("hard", "required-file", f"Missing deployment file: {relative}"))
    if missing:
        return findings

    compose = _read(root, "docker-compose.yml")
    dockerfile = _read(root, "Dockerfile")
    dockerignore = _read(root, ".dockerignore")
    env_example = _read(root, ".env.example")
    findings.extend(_decision_doc_findings(root))

    for relative, text in {
        "docker-compose.yml": compose,
        "Dockerfile": dockerfile,
        ".env.example": env_example,
    }.items():
        findings.extend(_secret_findings(relative, text))

    paper_block = _service_block(compose, "paper")
    live_block = _service_block(compose, "live")
    dashboard_block = _service_block(compose, "dashboard")
    openclaw_block = _service_block(compose, "openclaw")

    if "profiles:" not in paper_block or "- trading" not in paper_block:
        findings.append(Finding("hard", "trading-profile", "paper service must stay behind the trading profile."))
    if "profiles:" not in live_block or "- trading" not in live_block:
        findings.append(Finding("hard", "trading-profile", "live service must stay behind the trading profile."))
    if "scripts/run_live.py" in dashboard_block or "scripts/run_paper.py" in dashboard_block:
        findings.append(Finding("hard", "dashboard-command", "dashboard service must not start paper/live scripts."))
    if "APP_ENV=${APP_ENV:-development}" not in compose:
        findings.append(
            Finding("hard", "app-env-default", "dashboard APP_ENV must remain explicit and non-production by default.")
        )
    if "OPENAI_API_KEY=${OPENAI_API_KEY:-}" not in compose:
        findings.append(Finding("hard", "secret-env", "OPENAI_API_KEY must be injected from environment, not literal."))
    if "QUANT_SYSTEM_API_KEY=${QUANT_SYSTEM_API_KEY:-}" not in compose:
        findings.append(
            Finding("hard", "secret-env", "QUANT_SYSTEM_API_KEY must be injected from environment, not literal.")
        )
    if "OPENCLAW_AUTO_START=${OPENCLAW_AUTO_START:-false}" not in compose:
        findings.append(Finding("hard", "openclaw-autostart", "OpenClaw auto-start must remain false by default."))

    if "openclaw gateway run" in openclaw_block and "--auth none" in openclaw_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-auth",
                "OpenClaw gateway must not use --auth none in compose.",
            )
        )
    if "openclaw gateway run" in openclaw_block and (
        "--auth token" not in openclaw_block or "--token" not in openclaw_block
    ):
        findings.append(
            Finding(
                "hard",
                "openclaw-auth",
                "OpenClaw gateway compose command must use token auth.",
            )
        )
    if '"bind": "0.0.0.0"' not in openclaw_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-bind",
                "OpenClaw compose gateway must bind 0.0.0.0 so the dashboard container can reach it.",
            )
        )
    if "OPENCLAW_API_KEY=${OPENCLAW_API_KEY:-}" not in openclaw_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-secret-env",
                "OpenClaw service must receive OPENCLAW_API_KEY from the environment.",
            )
        )
    if "OPENCLAW_GATEWAY_TOKEN=${OPENCLAW_API_KEY:-}" not in openclaw_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-secret-env",
                "OpenClaw service must map OPENCLAW_GATEWAY_TOKEN from OPENCLAW_API_KEY.",
            )
        )
    if "OPENCLAW_API_KEY=${OPENCLAW_API_KEY:-}" not in dashboard_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-secret-env",
                "Dashboard service must receive OPENCLAW_API_KEY from the environment.",
            )
        )
    if "OPENCLAW_WEB_URL=${OPENCLAW_WEB_URL:-}" not in dashboard_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-web-url",
                "Dashboard OPENCLAW_WEB_URL must stay empty by default unless a controlled external panel URL is configured.",
            )
        )
    if '"18789:18789"' in openclaw_block or "ports:" in openclaw_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-port",
                "OpenClaw gateway must not publish host port 18789 by default; expose it only to the compose network.",
            )
        )
    if "expose:" not in openclaw_block or '- "18789"' not in openclaw_block:
        findings.append(
            Finding(
                "hard",
                "openclaw-port",
                "OpenClaw service must expose port 18789 only on the compose network.",
            )
        )

    if "python:3.11-slim" not in dockerfile:
        findings.append(Finding("hard", "docker-python", "Dockerfile should keep the documented Python 3.11 baseline."))
    if 'CMD ["python", "scripts/run_dashboard.py", "--port", "8001"]' not in dockerfile:
        findings.append(Finding("hard", "docker-cmd", "Dockerfile default CMD must start only the dashboard."))

    for ignored in ["data/", "logs/", "models/", ".venv/", "test-results/"]:
        if ignored not in dockerignore:
            findings.append(Finding("hard", "dockerignore", f".dockerignore must exclude {ignored}"))

    if "QUANT_SYSTEM_API_KEY=" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must document QUANT_SYSTEM_API_KEY."))
    if "OPENAI_API_KEY=" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must document OPENAI_API_KEY."))
    if "APP_ENV=development" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must default APP_ENV to development."))
    if "OPENCLAW_MANAGED=false" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must default OPENCLAW_MANAGED to false."))
    if "OPENCLAW_AUTO_START=false" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must default OPENCLAW_AUTO_START to false."))
    if "OPENCLAW_GATEWAY_URL=" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must document OPENCLAW_GATEWAY_URL."))
    if "OPENCLAW_WEB_URL=" not in env_example:
        findings.append(Finding("hard", "env-example", ".env.example must document OPENCLAW_WEB_URL."))
    if "OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789" in env_example:
        findings.append(
            Finding(
                "hard",
                "env-example",
                ".env.example must leave OPENCLAW_GATEWAY_URL empty so Docker uses the compose service default.",
            )
        )
    if "OPENCLAW_WEB_URL=http://127.0.0.1:18789" in env_example:
        findings.append(
            Finding(
                "hard",
                "env-example",
                ".env.example must leave OPENCLAW_WEB_URL empty unless a controlled external panel URL is configured.",
            )
        )
    if "IWENCAI_COOKIE=" not in env_example:
        findings.append(Finding("soft", "provider-boundary", ".env.example does not document IWENCAI_COOKIE boundary."))

    return findings


def _print_findings(findings: list[Finding], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"findings": [asdict(item) for item in findings]}, ensure_ascii=False, indent=2))
        return
    if not findings:
        print("Deployment static preflight OK")
        return
    print("Deployment static preflight findings:")
    for item in findings:
        print(f"- [{item.severity}] {item.check}: {item.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run static deployment checks without starting Docker.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--json", action="store_true", help="Print findings as JSON.")
    parser.add_argument("--fail-on-soft", action="store_true", help="Treat soft production-readiness findings as failures.")
    parser.add_argument("--production", action="store_true", help="Production readiness alias for --fail-on-soft.")
    args = parser.parse_args(argv)

    findings = run_checks(Path(args.root).resolve())
    _print_findings(findings, as_json=args.json)
    has_hard = any(item.severity == "hard" for item in findings)
    has_soft = any(item.severity == "soft" for item in findings)
    return 1 if has_hard or ((args.fail_on_soft or args.production) and has_soft) else 0


if __name__ == "__main__":
    raise SystemExit(main())
