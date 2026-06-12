#!/usr/bin/env python3
"""Run the local, non-deploying release preflight gates."""
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


PYTHON = ".venv/bin/python"
DEFAULT_EVIDENCE_PATH = "docs/release-evidence/2026-06-12-local-delivery-readiness.md"
RELEASE_BASE_SEARCH_DEPTH = 12


@dataclass(frozen=True)
class PreflightStep:
    label: str
    command: tuple[str, ...]
    writes_reports: bool = False


def build_preflight_plan(
    *,
    with_audits: bool = False,
    with_deployment_static: bool = False,
    with_production_static: bool = False,
    with_production_env: bool = False,
) -> list[PreflightStep]:
    """Return the ordered local preflight plan.

    The default plan intentionally avoids Docker, dev servers, real providers,
    external LLM/OpenClaw calls, trading scripts, and production config changes.
    """
    plan = [
        PreflightStep("context-pack", (PYTHON, "scripts/verify_context_pack.py")),
        PreflightStep(
            "release-evidence",
            (PYTHON, "scripts/release_preflight.py", "--verify-evidence"),
        ),
        PreflightStep("pytest", (PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider")),
        PreflightStep("compileall", (PYTHON, "-m", "compileall", "-q", ".")),
        PreflightStep("diff-check", ("git", "diff", "--check")),
    ]
    if with_audits:
        plan.extend(
            [
                PreflightStep(
                    "dashboard-data-health",
                    (PYTHON, "scripts/dashboard_data_health.py"),
                    writes_reports=True,
                ),
                PreflightStep(
                    "frontend-render-audit",
                    (PYTHON, "scripts/frontend_data_render_audit.py"),
                    writes_reports=True,
                ),
            ]
        )
    if with_production_static:
        plan.append(
            PreflightStep(
                "deployment-production-static",
                (PYTHON, "scripts/deployment_static_preflight.py", "--production"),
            )
        )
    elif with_deployment_static:
        plan.append(
            PreflightStep(
                "deployment-static",
                (PYTHON, "scripts/deployment_static_preflight.py"),
            )
        )
    if with_production_env:
        plan.append(
            PreflightStep(
                "production-env",
                (PYTHON, "scripts/production_env_preflight.py", "--profile", "all"),
            )
        )
    return plan


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _print_plan(plan: list[PreflightStep]) -> None:
    print("Release preflight plan")
    for index, step in enumerate(plan, start=1):
        report_note = " (writes test-results report)" if step.writes_reports else ""
        print(f"{index}. {step.label}{report_note}: {_format_command(step.command)}")


def run_preflight(plan: list[PreflightStep], *, cwd: Path) -> int:
    for step in plan:
        print(f"RUN {step.label}: {_format_command(step.command)}", flush=True)
        result = subprocess.run(step.command, cwd=cwd)
        if result.returncode != 0:
            print(f"FAILED {step.label}: exit {result.returncode}")
            return result.returncode
        print(f"PASS {step.label}")
    print("Release preflight OK")
    return 0


def _run_capture(command: tuple[str, ...], *, cwd: Path) -> list[str]:
    result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_ref_exists(ref: str, *, root: Path) -> bool:
    return (
        subprocess.run(
            ("git", "rev-parse", "--verify", "--quiet", ref),
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _path_exists_in_ref(ref: str, path: str, *, root: Path) -> bool:
    return (
        subprocess.run(
            ("git", "cat-file", "-e", f"{ref}:{path}"),
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _candidate_delta_bases(*, root: Path, evidence_path: str, base_ref: str | None) -> list[str]:
    if base_ref:
        return [base_ref]
    bases = ["HEAD"]
    if _path_exists_in_ref("HEAD", evidence_path, root=root):
        for depth in range(1, RELEASE_BASE_SEARCH_DEPTH + 1):
            ref = "HEAD" + "^" * depth
            if _git_ref_exists(ref, root=root):
                bases.append(ref)
    return bases


def _current_release_delta(
    *,
    root: Path,
    base: str,
) -> tuple[set[str], set[str]]:
    """Return modified and new files relative to the release base.

    A release handoff can be verified before or after `git add`. Plain
    `git diff --name-only` intentionally ignores staged files, so use HEAD as
    the comparison base for a dirty tree. After the release evidence has been
    committed, use the parent commit as the default base so the same evidence
    can verify the committed release delta.
    """
    all_changed = set(_run_capture(("git", "diff", "--name-only", base, "--"), cwd=root))
    added_from_base = set(_run_capture(("git", "diff", "--name-only", "--diff-filter=A", base, "--"), cwd=root))
    untracked_new = set(_run_capture(("git", "ls-files", "--others", "--exclude-standard"), cwd=root))
    current_new = added_from_base | untracked_new
    return all_changed - current_new, current_new


def _release_evidence_issues_for_delta(
    *,
    documented_modified: set[str],
    documented_new: set[str],
    current_modified: set[str],
    current_new: set[str],
) -> list[str]:
    issues: list[str] = []
    missing_modified = sorted(current_modified - documented_modified)
    stale_modified = sorted(documented_modified - current_modified)
    missing_new = sorted(current_new - documented_new)
    stale_new = sorted(documented_new - current_new)

    if missing_modified:
        issues.append("Modified files missing from release evidence: " + ", ".join(missing_modified))
    if stale_modified:
        issues.append("Release evidence lists modified files not in current diff: " + ", ".join(stale_modified))
    if missing_new:
        issues.append("New files missing from release evidence: " + ", ".join(missing_new))
    if stale_new:
        issues.append("Release evidence lists new files not currently untracked: " + ", ".join(stale_new))
    return issues


def _extract_text_block(text: str, heading: str) -> set[str]:
    pattern = re.compile(
        rf"{re.escape(heading)}:\n\n```text\n(?P<body>.*?)\n```",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return set()
    return {line.strip() for line in match.group("body").splitlines() if line.strip()}


def verify_release_evidence(
    *,
    root: Path,
    evidence_path: str = DEFAULT_EVIDENCE_PATH,
    base_ref: str | None = None,
) -> list[str]:
    evidence_file = root / evidence_path
    if not evidence_file.exists():
        return [f"Missing release evidence document: {evidence_path}"]

    text = evidence_file.read_text(encoding="utf-8")
    documented_modified = _extract_text_block(text, "Modified files currently in the delivery delta")
    documented_new = _extract_text_block(text, "New files that must be included in a staging/release bundle")
    candidate_issues: list[list[str]] = []
    for base in _candidate_delta_bases(root=root, evidence_path=evidence_path, base_ref=base_ref):
        current_modified, current_new = _current_release_delta(root=root, base=base)
        issues_for_base = _release_evidence_issues_for_delta(
            documented_modified=documented_modified,
            documented_new=documented_new,
            current_modified=current_modified,
            current_new=current_new,
        )
        if not issues_for_base:
            candidate_issues = []
            break
        candidate_issues.append(issues_for_base)
    issues = min(candidate_issues, key=len) if candidate_issues else []
    if "not a production deployment approval" not in text:
        issues.append("Release evidence must state that it is not a production deployment approval.")
    return issues


def _print_evidence_issues(issues: list[str]) -> None:
    if not issues:
        print("Release evidence OK")
        return
    print("Release evidence issues:")
    for issue in issues:
        print(f"- {issue}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local release preflight gates.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without running commands.")
    parser.add_argument(
        "--verify-evidence",
        action="store_true",
        help="Verify release evidence covers current modified and untracked files.",
    )
    parser.add_argument(
        "--evidence",
        default=DEFAULT_EVIDENCE_PATH,
        help="Release evidence document to verify.",
    )
    parser.add_argument(
        "--base-ref",
        help="Optional Git base ref for release evidence delta verification.",
    )
    parser.add_argument(
        "--with-audits",
        action="store_true",
        help="Also run report-writing dashboard/frontend audit scripts.",
    )
    parser.add_argument(
        "--with-deployment-static",
        action="store_true",
        help="Also run static deployment checks without starting Docker.",
    )
    parser.add_argument(
        "--with-production-static",
        action="store_true",
        help="Also run production static deployment checks and fail on production soft findings.",
    )
    parser.add_argument(
        "--with-production-env",
        action="store_true",
        help="Also check required production environment variables without printing secret values.",
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if args.verify_evidence:
        issues = verify_release_evidence(root=root, evidence_path=args.evidence, base_ref=args.base_ref)
        _print_evidence_issues(issues)
        return 1 if issues else 0

    plan = build_preflight_plan(
        with_audits=args.with_audits,
        with_deployment_static=args.with_deployment_static,
        with_production_static=args.with_production_static,
        with_production_env=args.with_production_env,
    )
    if args.dry_run:
        _print_plan(plan)
        return 0
    return run_preflight(plan, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
