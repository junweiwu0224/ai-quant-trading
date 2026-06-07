#!/usr/bin/env python3
"""Verify the Codex repo context pack without starting app services."""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_FILES = (
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/commands.md",
    "docs/testing.md",
    "docs/quality-gates.md",
    "docs/subagents.md",
    "docs/codex-usage.md",
    "docs/codex-playbook.md",
    "docs/glossary.md",
    "docs/decisions/README.md",
    "docs/decisions/0000-template.md",
    "docs/specs/README.md",
    "docs/specs/0001-template.md",
)

TEXT_FILES = (
    "AGENTS.md",
    "docs/commands.md",
    "docs/testing.md",
    "docs/quality-gates.md",
    "docs/subagents.md",
    "docs/codex-usage.md",
    "docs/codex-playbook.md",
    "docs/glossary.md",
    "docs/decisions/README.md",
    "docs/decisions/0000-template.md",
    "docs/specs/README.md",
    "docs/specs/0001-template.md",
)

BARE_PYTHON_RE = re.compile(r"(^|[`>\s])python( -m| scripts/)")
SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9]{20,}|BEGIN (?:RSA|OPENSSH|PRIVATE) KEY|"
    r"(?:api[_-]?key|secret|password)\s*=",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class ContextPackIssue:
    severity: str
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _existing_text_files(root: Path) -> Iterable[tuple[str, str]]:
    for relative in TEXT_FILES:
        path = root / relative
        if path.exists() and path.is_file():
            yield relative, _read_text(path)


def _line_has_bare_python(line: str) -> bool:
    if ".venv/bin/python" in line or "python3" in line:
        return False
    return bool(BARE_PYTHON_RE.search(line))


def _is_usage_history(path: str) -> bool:
    return path == "docs/codex-usage.md"


def _has_usage_review_mechanism(text: str) -> bool:
    return "周期复盘" in text or "阶段复盘" in text


def check_context_pack(root: str | Path = ".") -> list[ContextPackIssue]:
    root = Path(root)
    issues: list[ContextPackIssue] = []

    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.exists():
            issues.append(
                ContextPackIssue(
                    severity="error",
                    code="missing-required-file",
                    path=relative,
                    message="Required context pack file is missing.",
                )
            )

    upper_arch = root / "docs/ARCHITECTURE.md"
    lower_arch = root / "docs/architecture.md"
    if upper_arch.exists() and lower_arch.exists():
        try:
            same_file = upper_arch.samefile(lower_arch)
        except OSError:
            same_file = False
        if not same_file:
            issues.append(
                ContextPackIssue(
                    severity="error",
                    code="architecture-case-duplicate",
                    path="docs/architecture.md",
                    message="Do not create lowercase architecture docs when docs/ARCHITECTURE.md exists.",
                )
            )

    agents_text = _read_text(root / "AGENTS.md") if (root / "AGENTS.md").exists() else ""
    if "docs/ARCHITECTURE.md" not in agents_text:
        issues.append(
            ContextPackIssue(
                severity="error",
                code="missing-architecture-reference",
                path="AGENTS.md",
                message="AGENTS.md must reference docs/ARCHITECTURE.md.",
            )
        )
    if "docs/architecture.md" in agents_text:
        issues.append(
            ContextPackIssue(
                severity="error",
                code="architecture-case-reference",
                path="AGENTS.md",
                message="Use docs/ARCHITECTURE.md, not docs/architecture.md.",
            )
        )
    if "npm test" not in agents_text or "占位" not in agents_text:
        issues.append(
            ContextPackIssue(
                severity="error",
                code="missing-npm-test-warning",
                path="AGENTS.md",
                message="AGENTS.md must warn that npm test is a placeholder failure.",
            )
        )

    usage_path = root / "docs/codex-usage.md"
    if usage_path.exists() and not _has_usage_review_mechanism(_read_text(usage_path)):
        issues.append(
            ContextPackIssue(
                severity="error",
                code="missing-usage-review",
                path="docs/codex-usage.md",
                message="docs/codex-usage.md must include periodic or stage review guidance.",
            )
        )

    for relative, text in _existing_text_files(root):
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _line_has_bare_python(line) and not _is_usage_history(relative):
                issues.append(
                    ContextPackIssue(
                        severity="error",
                        code="bare-python-command",
                        path=relative,
                        message=f"Line {line_number} uses an unverified python command: {line.strip()}",
                    )
                )
            if SECRET_RE.search(line):
                issues.append(
                    ContextPackIssue(
                        severity="error",
                        code="sensitive-pattern",
                        path=relative,
                        message=f"Line {line_number} looks like it contains a secret or endpoint value.",
                    )
                )

    return sorted(issues)


def build_report(root: str | Path = ".") -> dict[str, object]:
    issues = check_context_pack(root)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    return {
        "ok": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": [issue.to_dict() for issue in issues],
    }


def _print_report(report: dict[str, object]) -> None:
    if report["ok"]:
        print("Context pack OK")
        return

    print(f"Context pack issues: {report['error_count']} error(s), {report['warning_count']} warning(s)")
    for issue in report["issues"]:
        print(f"[{issue['severity']}] {issue['code']} {issue['path']}: {issue['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Codex context pack files.")
    parser.add_argument("root", nargs="?", default=".", help="Repository root to verify.")
    args = parser.parse_args(argv)

    report = build_report(args.root)
    _print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
