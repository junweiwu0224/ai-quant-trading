#!/usr/bin/env python3
"""Verify production release decision records without exposing secret values."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_TEMPLATE = "docs/release-evidence/production-release-decision-template.md"

REQUIRED_SECTIONS = [
    "Release Identity",
    "Local Evidence Gate",
    "Production Environment Gate",
    "Production Auth Boundary Gate",
    "OpenClaw Auth And Network Gate",
    "Docker Compose Gate",
    "Real Provider / iWencai Gate",
    "OpenClaw / LLM Gate",
    "Data Sync And Migration Gate",
    "Paper / Live / Broker Gate",
    "Final Decision",
]

REQUIRED_FIELDS = [
    "日期",
    "Branch",
    "Commit SHA",
    "Bundle path",
    "Bundle checksum file",
    "Release evidence",
    "决策状态",
    "决策人 / owner",
    "`git status --short`",
    "`.venv/bin/python scripts/release_preflight.py --verify-evidence`",
    "`.venv/bin/python scripts/build_release_bundle.py --verify-only`",
    "`.venv/bin/python scripts/deployment_static_preflight.py`",
    "`.venv/bin/python scripts/deployment_static_preflight.py --production`",
    "`.venv/bin/python scripts/production_env_preflight.py --profile all`",
    "`.venv/bin/python scripts/production_auth_preflight.py`",
    "`docker compose config`",
    "`docker compose up -d --build dashboard openclaw`",
    "Dashboard health smoke",
    "是否使用真实 cookie/token",
    "`provider_status` / `source_status` / `parsed_conditions` / `candidate_provenance`",
    "外部服务地址和认证范围",
    "`/api/openclaw/status`",
    "数据目录",
    "备份位置",
    "回滚方式",
    "Approved / Rejected / Deferred",
    "回滚负责人",
    "下一次复核日期",
]

GATE_SECTIONS = [
    "Local Evidence Gate",
    "Production Environment Gate",
    "Production Auth Boundary Gate",
    "OpenClaw Auth And Network Gate",
    "Docker Compose Gate",
    "Real Provider / iWencai Gate",
    "OpenClaw / LLM Gate",
    "Data Sync And Migration Gate",
    "Paper / Live / Broker Gate",
]

PLACEHOLDER_VALUES = {
    "",
    "todo",
    "tbd",
    "n/a",
    "na",
    "待填",
    "待定",
    "未填",
    "none",
    "null",
}
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|cookie)\b\s*[:：=]\s*(?!`?\s*(?:yes|no|是|否|present|missing|not approved|approved|operator|确认|未记录|未使用|使用|not used|redacted)\b)([^`\s，。；;]+)"
    r"|Bearer\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|sk-[A-Za-z0-9]{16,}"
)


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    message: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section_text(text: str, section: str) -> str:
    pattern = re.compile(rf"(?ms)^## {re.escape(section)}\n(?P<body>.*?)(?=^## |\Z)")
    match = pattern.search(text)
    return match.group("body").strip() if match else ""


def _field_value(section_body: str, field: str) -> str | None:
    pattern = re.compile(rf"(?m)^\s*-\s+{re.escape(field)}[^\S\r\n]*[:：][^\S\r\n]*(?P<value>.*)$")
    match = pattern.search(section_body)
    if not match:
        return None
    return match.group("value").strip()


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    cleaned = value.strip().strip("`").strip()
    return cleaned.lower() in PLACEHOLDER_VALUES


def _is_missing_required_risk_value(value: str | None) -> bool:
    if _is_placeholder(value):
        return True
    return value is not None and value.strip().strip("`").strip().lower() in {"none", "无"}


def _line_number(text: str, needle: str) -> int:
    before = text.split(needle, 1)[0]
    return before.count("\n") + 1


def _secret_findings(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in text.splitlines():
        if not SECRET_ASSIGNMENT_RE.search(line):
            continue
        findings.append(
            Finding(
                "hard",
                "secret-redaction",
                f"{path}:{_line_number(text, line)} appears to contain a literal secret-like value.",
            )
        )
    return findings


def verify_template(path: Path) -> list[Finding]:
    if not path.is_file():
        return [Finding("hard", "required-file", f"Missing production release decision template: {path}")]
    text = _read(path)
    findings: list[Finding] = []
    for section in REQUIRED_SECTIONS:
        if not _section_text(text, section):
            findings.append(Finding("hard", "required-section", f"Missing section: {section}"))
    for field in REQUIRED_FIELDS:
        if f"- {field}" not in text:
            findings.append(Finding("hard", "required-field", f"Missing release decision field: {field}"))
    if "不得在本记录中填写 secret 原文" not in text:
        findings.append(
            Finding(
                "hard",
                "secret-instruction",
                "Decision template must explicitly forbid recording secret values.",
            )
        )
    findings.extend(_secret_findings(path, text))
    return findings


def verify_decision(path: Path) -> list[Finding]:
    if not path.is_file():
        return [Finding("hard", "required-file", f"Missing production release decision record: {path}")]
    text = _read(path)
    findings = verify_template(path)
    findings.extend(_filled_field_findings(text))
    findings.extend(_gate_conclusion_findings(text))
    findings.extend(_final_decision_findings(text))
    findings.extend(_risk_acceptance_findings(text))
    return findings


def _filled_field_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for section in ["Release Identity", "Final Decision"]:
        body = _section_text(text, section)
        for line in body.splitlines():
            if not line.startswith("- ") or "：" not in line and ":" not in line:
                continue
            field = line[2:].split("：", 1)[0].split(":", 1)[0].strip()
            value = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
            if _is_placeholder(value):
                findings.append(
                    Finding("hard", "required-value", f"{section} field is not filled: {field}")
                )
    return findings


def _gate_conclusion_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for section in GATE_SECTIONS:
        body = _section_text(text, section)
        conclusion = re.search(r"(?m)^结论[:：]\s*(?P<value>.*)$", body)
        if not conclusion or _is_placeholder(conclusion.group("value")):
            findings.append(Finding("hard", "gate-conclusion", f"Gate conclusion is not filled: {section}"))
    return findings


def _final_decision_findings(text: str) -> list[Finding]:
    body = _section_text(text, "Final Decision")
    value = _field_value(body, "Approved / Rejected / Deferred")
    cleaned = (value or "").strip().strip("`")
    if value is None or cleaned not in {"Approved", "Rejected", "Deferred"}:
        return [
            Finding(
                "hard",
                "final-decision",
                "Final Decision must choose Approved, Rejected, or Deferred.",
            )
        ]
    return []


def _risk_acceptance_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    openclaw = _section_text(text, "OpenClaw Auth And Network Gate")
    solution = _field_value(openclaw, "解决方式")
    accepts_risk = bool(solution and re.search(r"临时接受|accepted risk|temporar", solution, re.IGNORECASE))
    if accepts_risk:
        for field in ["Owner", "到期时间", "补偿控制", "回滚命令"]:
            value = _field_value(openclaw, field)
            if _is_missing_required_risk_value(value):
                findings.append(
                    Finding("hard", "risk-acceptance", f"Temporary OpenClaw risk acceptance missing: {field}")
                )

    final = _section_text(text, "Final Decision")
    accepted_risks = _field_value(final, "被临时接受的风险")
    if accepted_risks and not _is_placeholder(accepted_risks) and accepted_risks.lower() not in {"none", "无"}:
        for field in ["风险接受到期时间", "回滚负责人", "下一次复核日期"]:
            value = _field_value(final, field)
            if _is_missing_required_risk_value(value):
                findings.append(
                    Finding("hard", "risk-acceptance", f"Accepted final risk missing: {field}")
                )
    return findings


def _print_findings(findings: list[Finding], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"findings": [asdict(item) for item in findings]}, ensure_ascii=False, indent=2))
        return
    if not findings:
        print("Production release decision OK")
        return
    print("Production release decision findings:")
    for item in findings:
        print(f"- [{item.severity}] {item.check}: {item.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify production release decision template or filled record.")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="Production release decision template path.")
    parser.add_argument("--decision", help="Filled production release decision record to verify.")
    parser.add_argument("--json", action="store_true", help="Print findings as JSON.")
    args = parser.parse_args(argv)

    findings = verify_decision(Path(args.decision)) if args.decision else verify_template(Path(args.template))
    _print_findings(findings, as_json=args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
