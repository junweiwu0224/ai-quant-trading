#!/usr/bin/env python3
"""Static production auth checks that do not import the FastAPI app."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


REQUIRED_TESTS = {
    "tests/test_session_gate.py": [
        "test_session_gate_allows_api_requests_in_test_environment",
        "test_settings_respect_existing_app_env",
    ],
    "tests/test_openclaw_account.py": [
        "test_production_does_not_bootstrap_known_default_invite",
        "test_session_cookie_is_secure_in_production",
    ],
}


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    message: str


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _missing_file_findings(root: Path, files: list[str]) -> list[Finding]:
    return [
        Finding("hard", "required-file", f"Missing required auth boundary file: {relative}")
        for relative in files
        if not (root / relative).is_file()
    ]


def _app_auth_findings(app_text: str) -> list[Finding]:
    findings: list[Finding] = []
    if 'os.environ.get("APP_ENV") == "test"' not in app_text:
        findings.append(
            Finding(
                "hard",
                "test-only-session-bypass",
                "SessionGateMiddleware must restrict the API session bypass to APP_ENV=test.",
            )
        )
    if "if api_key_enabled() and is_valid_api_key(request_api_key(request)):" not in app_text:
        findings.append(
            Finding(
                "hard",
                "api-key-session-bypass",
                "SessionGateMiddleware must allow configured API-key auth before cookie auth.",
            )
        )
    if "request.cookies.get(\"quant_session\")" not in app_text:
        findings.append(
            Finding(
                "hard",
                "session-cookie-gate",
                "SessionGateMiddleware must check the quant_session cookie before protected API access.",
            )
        )
    if "account_store.get_user_by_session(token)" not in app_text:
        findings.append(
            Finding(
                "hard",
                "session-store-validation",
                "SessionGateMiddleware must validate quant_session against AccountStore.",
            )
        )
    if "api_key_enabled()" not in app_text or "app.add_middleware(APIKeyMiddleware)" not in app_text:
        findings.append(
            Finding(
                "hard",
                "api-key-middleware",
                "APIKeyMiddleware must be installed when QUANT_SYSTEM_API_KEY is configured.",
            )
        )
    if '["https://biga.junwei.fun"]' not in app_text or 'if _ENV == "production"' not in app_text:
        findings.append(
            Finding(
                "hard",
                "production-cors",
                "Production CORS must be restricted to the approved HTTPS origin.",
            )
        )
    production_cors_match = re.search(
        r"_origins\s*=\s*\(\s*\[(?P<prod>[^\]]+)\]\s*if\s+_ENV\s*==\s*[\"']production[\"']",
        app_text,
        re.DOTALL,
    )
    if not production_cors_match:
        findings.append(
            Finding("hard", "production-cors", "Could not locate the production CORS origin branch.")
        )
    elif "localhost" in production_cors_match.group("prod") or "127.0.0.1" in production_cors_match.group("prod"):
        findings.append(
            Finding("hard", "production-cors", "Production CORS branch must not include localhost origins.")
        )
    return findings


def _session_findings(session_text: str) -> list[Finding]:
    findings: list[Finding] = []
    if 'os.getenv("APP_ENV", "development").lower() == "production"' not in session_text:
        findings.append(
            Finding(
                "hard",
                "secure-session-cookie",
                "Session cookie secure flag must be enabled when APP_ENV=production.",
            )
        )
    for required in ['"httponly": True', '"samesite": "lax"', '"path": "/"']:
        if required not in session_text:
            findings.append(
                Finding(
                    "hard",
                    "session-cookie-options",
                    f"Session cookie options must include {required}.",
                )
            )
    return findings


def _auth_helper_findings(auth_text: str) -> list[Finding]:
    findings: list[Finding] = []
    if "secrets.compare_digest(candidate, expected)" not in auth_text:
        findings.append(
            Finding(
                "hard",
                "constant-time-api-key",
                "API key comparison must use secrets.compare_digest.",
            )
        )
    if 'API_KEY_HEADER = "X-API-Key"' not in auth_text:
        findings.append(Finding("hard", "api-key-header", "API key header must remain X-API-Key."))
    if 'request.headers.get("Authorization", "")' not in auth_text:
        findings.append(
            Finding(
                "hard",
                "bearer-api-key",
                "HTTP requests must support Authorization: Bearer API keys.",
            )
        )
    if 'ws.query_params.get("token")' not in auth_text or 'ws.query_params.get("api_key")' not in auth_text:
        findings.append(
            Finding(
                "hard",
                "websocket-api-key",
                "WebSocket API key auth must support api_key/token query params.",
            )
        )
    return findings


def _account_store_findings(account_store_text: str) -> list[Finding]:
    findings: list[Finding] = []
    if 'os.getenv("APP_ENV", "development").lower() == "production"' not in account_store_text:
        findings.append(
            Finding(
                "hard",
                "production-invite-bootstrap",
                "AccountStore must detect APP_ENV=production before invite bootstrap.",
            )
        )
    if "return" not in account_store_text.partition('elif os.getenv("APP_ENV", "development").lower() == "production":')[2][:120]:
        findings.append(
            Finding(
                "hard",
                "production-invite-bootstrap",
                "Production invite bootstrap must return before creating a default local invite code.",
            )
        )
    if "hash_session_token(token)" not in account_store_text:
        findings.append(
            Finding("hard", "session-token-hash", "Sessions must be stored/looked up by hashed session token.")
        )
    if "hash_invite_code(code)" not in account_store_text:
        findings.append(
            Finding("hard", "invite-code-hash", "Invite codes must be stored/looked up by hash.")
        )
    registration_audit = account_store_text.partition("auth.register")[2][:500]
    if "invite_code_hash" not in registration_audit or re.search(r"['\"]invite_code['\"]\s*:", registration_audit):
        findings.append(
            Finding(
                "hard",
                "invite-audit-redaction",
                "Registration audit metadata must record invite_code_hash without plaintext invite_code.",
            )
        )
    return findings


def _test_coverage_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative, required_names in REQUIRED_TESTS.items():
        path = root / relative
        if not path.is_file():
            findings.append(Finding("hard", "auth-test-coverage", f"Missing auth boundary test file: {relative}"))
            continue
        text = path.read_text(encoding="utf-8")
        for name in required_names:
            if f"def {name}" not in text:
                findings.append(
                    Finding("hard", "auth-test-coverage", f"{relative} must include {name}.")
                )
    return findings


def run_checks(root: Path) -> list[Finding]:
    required = [
        "dashboard/app.py",
        "dashboard/auth.py",
        "dashboard/session.py",
        "dashboard/account_store.py",
    ]
    findings = _missing_file_findings(root, required)
    if findings:
        return findings

    findings.extend(_app_auth_findings(_read(root, "dashboard/app.py")))
    findings.extend(_session_findings(_read(root, "dashboard/session.py")))
    findings.extend(_auth_helper_findings(_read(root, "dashboard/auth.py")))
    findings.extend(_account_store_findings(_read(root, "dashboard/account_store.py")))
    findings.extend(_test_coverage_findings(root))
    return findings


def _print_findings(findings: list[Finding], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"findings": [asdict(item) for item in findings]}, ensure_ascii=False, indent=2))
        return
    if not findings:
        print("Production auth preflight OK")
        return
    print("Production auth preflight findings:")
    for item in findings:
        print(f"- [{item.severity}] {item.check}: {item.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run static production auth checks without importing the app.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--json", action="store_true", help="Print findings as JSON.")
    args = parser.parse_args(argv)

    findings = run_checks(Path(args.root).resolve())
    _print_findings(findings, as_json=args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
