"""Static risk scan for dashboard frontend data rendering."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Pattern


@dataclass(frozen=True)
class RenderRisk:
    file: str
    line: int
    kind: str
    severity: str
    snippet: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "file": self.file,
            "line": self.line,
            "kind": self.kind,
            "severity": self.severity,
            "snippet": self.snippet,
        }


RISK_PATTERNS: tuple[tuple[str, str, Pattern[str]], ...] = (
    ("raw_to_fixed", "high", re.compile(r"\.toFixed\s*\(")),
    ("raw_number_constructor", "medium", re.compile(r"\bNumber\s*\(")),
    ("fallback_or_placeholder", "medium", re.compile(r"\|\|\s*(?:'--'|\"--\")")),
    ("direct_nan_check", "low", re.compile(r"\bisNaN\s*\(")),
)
DYNAMIC_INNER_HTML_PATTERN = re.compile(r"\.innerHTML\s*=.*?`[^`]*\$\{", re.DOTALL)


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("//") or stripped.startswith("*")


def _snippet(line: str) -> str:
    return line.strip()[:240]


def _posix_path(path: Path) -> str:
    return path.as_posix()


def scan_js_text(text: str, file_path: Path) -> list[RenderRisk]:
    risks: list[RenderRisk] = []
    file_name = _posix_path(file_path)
    stripped_lines = [
        "" if _is_comment_or_blank(line) else line for line in text.splitlines()
    ]
    stripped_text = "\n".join(stripped_lines)
    for line_number, line in enumerate(stripped_lines, start=1):
        if not line:
            continue
        for kind, severity, pattern in RISK_PATTERNS:
            if pattern.search(line):
                risks.append(
                    RenderRisk(
                        file=file_name,
                        line=line_number,
                        kind=kind,
                        severity=severity,
                        snippet=_snippet(line),
                    )
                )
    for match in DYNAMIC_INNER_HTML_PATTERN.finditer(stripped_text):
        line_number = stripped_text.count("\n", 0, match.start()) + 1
        risks.append(
            RenderRisk(
                file=file_name,
                line=line_number,
                kind="dynamic_inner_html",
                severity="medium",
                snippet=_snippet(stripped_lines[line_number - 1]),
            )
        )
    return risks


def scan_static_tree(root: Path) -> list[RenderRisk]:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Static audit root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Static audit root is not a directory: {root}")
    risks: list[RenderRisk] = []
    for path in sorted(root.rglob("*.js")):
        if "node_modules" in path.parts:
            continue
        relative_path = path.relative_to(root)
        risks.extend(
            scan_js_text(path.read_text(encoding="utf-8", errors="ignore"), relative_path)
        )
    return sorted(risks, key=lambda risk: (risk.file, risk.line, risk.kind))


def build_report(root: Path) -> dict[str, object]:
    root = Path(root)
    risks = scan_static_tree(root)
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for risk in risks:
        by_kind[risk.kind] = by_kind.get(risk.kind, 0) + 1
        by_severity[risk.severity] = by_severity.get(risk.severity, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "frontend_static",
        "root": root.as_posix(),
        "risk_count": len(risks),
        "by_kind": by_kind,
        "by_severity": by_severity,
        "risks": [risk.to_dict() for risk in risks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit frontend rendering risk patterns.")
    parser.add_argument("--root", default="dashboard/static")
    parser.add_argument(
        "--output",
        default="test-results/data-display-audit/frontend-static-report.json",
    )
    args = parser.parse_args(argv)

    report = build_report(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote frontend static data render report: {output}")
    print(f"Risks: {report['risk_count']}, by severity: {report['by_severity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
