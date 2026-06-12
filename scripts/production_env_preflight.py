#!/usr/bin/env python3
"""Read-only production environment checks that never print secret values."""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Mapping


PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change-me",
    "example",
    "local1",
    "placeholder",
    "test",
    "token",
    "your-api-key",
    "your-openai-api-key",
    "your-token",
}
SECRET_NAME_RE = re.compile(r"(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|COOKIE)", re.IGNORECASE)
URL_RE = re.compile(r"^https?://[^/\s#?]+(?:[/?#][^\s]*)?$", re.IGNORECASE)

PROFILE_ORDER = ("base", "docker", "llm", "provider")
PROFILE_ALIASES = {
    "all": PROFILE_ORDER,
    "base": ("base",),
    "docker": ("base", "docker"),
    "llm": ("base", "llm"),
    "provider": ("base", "provider"),
}


@dataclass(frozen=True)
class EnvRequirement:
    name: str
    profile: str
    description: str
    secret: bool = True
    min_length: int = 16
    expected: str | None = None
    kind: str = "secret"


@dataclass(frozen=True)
class Finding:
    severity: str
    profile: str
    variable: str
    status: str
    message: str


REQUIREMENTS = (
    EnvRequirement(
        "APP_ENV",
        "base",
        "Production deployments must opt in explicitly with APP_ENV=production.",
        secret=False,
        expected="production",
        kind="literal",
    ),
    EnvRequirement(
        "QUANT_SYSTEM_API_KEY",
        "base",
        "Public or production Dashboard/API access must require an operator-provided API key.",
        min_length=16,
    ),
    EnvRequirement(
        "OPENCLAW_API_KEY",
        "docker",
        "Docker/OpenClaw production must use token auth shared by dashboard and gateway.",
        min_length=16,
    ),
    EnvRequirement(
        "OPENAI_API_KEY",
        "llm",
        "LLM production smoke tests require an operator-provided OpenAI-compatible API key.",
        min_length=20,
    ),
    EnvRequirement(
        "OPENAI_BASE_URL",
        "llm",
        "LLM production smoke tests require an explicit OpenAI-compatible base URL.",
        secret=False,
        min_length=12,
        kind="url",
    ),
    EnvRequirement(
        "IWENCAI_COOKIE",
        "provider",
        "Real iWencai provider smoke tests require an approved read-only provider session cookie.",
        min_length=20,
    ),
)


def _normalize_profile_names(profiles: list[str] | None) -> tuple[str, ...]:
    requested = profiles or ["base"]
    expanded: list[str] = []
    for profile in requested:
        for item in PROFILE_ALIASES[profile]:
            if item not in expanded:
                expanded.append(item)
    return tuple(item for item in PROFILE_ORDER if item in expanded)


def _is_placeholder(value: str) -> bool:
    stripped = value.strip().strip("'\"")
    lowered = stripped.lower()
    if lowered in PLACEHOLDER_VALUES:
        return True
    return lowered.startswith("your-") or lowered.endswith("-placeholder")


def _check_requirement(requirement: EnvRequirement, env: Mapping[str, str]) -> Finding | None:
    raw_value = env.get(requirement.name)
    value = "" if raw_value is None else raw_value.strip()

    if not value:
        return Finding(
            "hard",
            requirement.profile,
            requirement.name,
            "missing",
            f"{requirement.name} is required for the {requirement.profile} production gate.",
        )
    if _is_placeholder(value):
        return Finding(
            "hard",
            requirement.profile,
            requirement.name,
            "placeholder",
            f"{requirement.name} must be replaced with an operator-managed value before this gate passes.",
        )
    if requirement.expected is not None and value != requirement.expected:
        return Finding(
            "hard",
            requirement.profile,
            requirement.name,
            "invalid_value",
            f"{requirement.name} must equal {requirement.expected} for this production gate.",
        )
    if requirement.kind == "url" and not URL_RE.match(value):
        return Finding(
            "hard",
            requirement.profile,
            requirement.name,
            "invalid_url",
            f"{requirement.name} must be an explicit http(s) URL for this production gate.",
        )
    if requirement.secret and len(value) < requirement.min_length:
        return Finding(
            "hard",
            requirement.profile,
            requirement.name,
            "too_short",
            f"{requirement.name} is present but too short for the {requirement.profile} production gate.",
        )
    return None


def run_checks(
    env: Mapping[str, str] | None = None,
    *,
    profiles: list[str] | None = None,
) -> list[Finding]:
    """Return production env findings without reading .env files or printing values."""
    active_profiles = set(_normalize_profile_names(profiles))
    environment = os.environ if env is None else env
    findings: list[Finding] = []
    for requirement in REQUIREMENTS:
        if requirement.profile not in active_profiles:
            continue
        finding = _check_requirement(requirement, environment)
        if finding is not None:
            findings.append(finding)
    return findings


def _safe_status_rows(
    env: Mapping[str, str],
    *,
    profiles: list[str] | None,
    findings: list[Finding],
) -> list[dict[str, str]]:
    finding_by_name = {finding.variable: finding for finding in findings}
    active_profiles = set(_normalize_profile_names(profiles))
    rows: list[dict[str, str]] = []
    for requirement in REQUIREMENTS:
        if requirement.profile not in active_profiles:
            continue
        finding = finding_by_name.get(requirement.name)
        status = finding.status if finding else "present"
        rows.append(
            {
                "profile": requirement.profile,
                "variable": requirement.name,
                "status": status,
                "secret": "yes" if requirement.secret or SECRET_NAME_RE.search(requirement.name) else "no",
                "description": requirement.description,
            }
        )
    return rows


def _print_report(
    findings: list[Finding],
    *,
    env: Mapping[str, str],
    profiles: list[str] | None,
    as_json: bool,
) -> None:
    rows = _safe_status_rows(env, profiles=profiles, findings=findings)
    if as_json:
        print(
            json.dumps(
                {
                    "profiles": list(_normalize_profile_names(profiles)),
                    "checks": rows,
                    "findings": [asdict(item) for item in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not findings:
        print("Production env preflight OK")
    else:
        print("Production env preflight findings:")
        for item in findings:
            print(f"- [{item.severity}] {item.profile}/{item.variable}: {item.status} - {item.message}")
    print("Checked variables:")
    for row in rows:
        print(f"- {row['profile']}/{row['variable']}: {row['status']} (secret={row['secret']})")
    print("Secret values were not printed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check production environment variables without reading .env files or printing secret values."
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PROFILE_ALIASES),
        help=(
            "Production gate to check. May be repeated. "
            "Default: base. docker/llm/provider include base; all checks every gate."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print sanitized JSON output.")
    args = parser.parse_args(argv)

    findings = run_checks(profiles=args.profile)
    _print_report(findings, env=os.environ, profiles=args.profile, as_json=args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
