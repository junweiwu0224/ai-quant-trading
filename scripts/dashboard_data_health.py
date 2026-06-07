"""Dashboard read-only API data health audit."""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


os.environ.setdefault("APP_ENV", "test")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HARD_BAD_STRINGS = frozenset(
    {
        "nan",
        "nan%",
        "undefined",
        "undefined%",
        "inf",
        "inf%",
        "infinity",
        "infinity%",
        "-inf",
        "-inf%",
        "-infinity",
        "-infinity%",
        "[object object]",
    }
)

SAFE_GET_PATHS = [
    "/api/system/status",
    "/api/system/strategies",
    "/api/system/risk/rules",
    "/api/backtest/strategies",
    "/api/backtest/stocks",
    "/api/portfolio/snapshot",
    "/api/portfolio/trades",
    "/api/portfolio/risk",
    "/api/paper/status",
    "/api/paper/orders",
    "/api/paper/positions",
    "/api/paper/performance",
    "/api/stock/search?q=600519&limit=5",
    "/api/stock/detail/600519",
    "/api/stock/kline/600519?period=daily&count=30",
    "/api/stock/market/indices",
    "/api/stock/market/stats",
    "/api/market/radar",
    "/api/market/breadth",
    "/api/market/news",
    "/api/market/sectors",
    "/api/market/heatmap",
    "/api/market/northbound",
    "/api/valuation/health",
    "/api/datahub/health",
    "/api/datahub/decision-matrix?scope=codes&codes=600519&limit=3&fast=true",
    "/api/signals/health",
    "/api/signals/top?limit=5",
    "/api/alerts/rules",
    "/api/conditional-orders/rules",
    "/api/alpha/model-status",
    "/api/alpha/formula/catalog",
    "/api/watchlist",
    "/api/qlib/health",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_AUDIT_ACCOUNT = {
    "id": "dashboard-data-health-audit",
    "username": "dashboard-data-health-audit",
    "display_name": "Dashboard Data Health Audit",
    "email": "",
    "role": "admin",
    "avatar_color": "#2f6fed",
    "created_at": "1970-01-01T00:00:00+00:00",
    "last_login_at": "",
    "disabled": False,
    "workspace": {
        "id": "dashboard-data-health-audit-workspace",
        "user_id": "dashboard-data-health-audit",
        "name": "Dashboard Data Health Audit",
        "slug": "dashboard-data-health-audit",
        "openclaw_workspace_id": "ocw_dashboard_data_health_audit",
        "settings": {},
        "created_at": "1970-01-01T00:00:00+00:00",
        "updated_at": "1970-01-01T00:00:00+00:00",
    },
    "permissions": {
        "chat": True,
        "read_market": True,
        "read_portfolio": True,
        "write_watchlist": False,
        "write_paper_trade": False,
        "manage_skills": False,
        "manage_workspace": False,
        "admin": True,
    },
}


@dataclass(frozen=True)
class AuditFinding:
    path: str
    kind: str
    value: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "kind": self.kind,
            "value": self.value,
            "severity": self.severity,
        }


def normalize_path_for_name(path: str) -> str:
    parsed = urlsplit(path)
    pieces = [parsed.path]
    if parsed.query:
        pieces.append(parsed.query)
    raw = "_".join(part for part in pieces if part)
    raw = raw.strip("/")
    raw = raw.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_")
    raw = re.sub(r"[^A-Za-z0-9]+", "_", raw)
    return raw.strip("_") or "root"


def _string_finding(value: str, path: str) -> AuditFinding | None:
    normalized = value.strip().lower()
    if normalized in HARD_BAD_STRINGS:
        return AuditFinding(path=path, kind="bad_display_string", value=value, severity="hard")
    return None


def _next_path(parent: str, key: Any) -> str:
    if isinstance(key, str) and _IDENTIFIER_RE.match(key):
        return f"{parent}.{key}"
    if isinstance(key, str):
        return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"
    return f"{parent}[{key}]"


def find_json_anomalies(value: Any, path: str = "$") -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    if isinstance(value, bool) or value is None:
        return findings

    if isinstance(value, float):
        if not math.isfinite(value):
            findings.append(
                AuditFinding(path=path, kind="non_finite_number", value=str(value), severity="hard")
            )
        return findings

    if isinstance(value, int):
        return findings

    if isinstance(value, str):
        finding = _string_finding(value, path)
        if finding:
            findings.append(finding)
        return findings

    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(find_json_anomalies(child, _next_path(path, key)))
        return findings

    if isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_json_anomalies(child, f"{path}[{index}]"))
        return findings

    return findings


def _response_payload(response) -> tuple[bool, Any, str]:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return False, None, content_type
    return True, response.json(), content_type


async def _audit_account_override() -> dict[str, Any]:
    return _AUDIT_ACCOUNT


def _import_dashboard_session():
    try:
        return importlib.import_module("dashboard.session")
    except ModuleNotFoundError as exc:
        if exc.name == "dashboard.session":
            return None
        raise


def _install_account_overrides(app) -> dict[Any, Any]:
    session = _import_dashboard_session()
    if session is None:
        return {}

    previous: dict[Any, Any] = {}
    for dependency_name in ("current_account", "optional_account"):
        dependency = getattr(session, dependency_name, None)
        if dependency is None:
            continue
        if dependency in app.dependency_overrides:
            previous[dependency] = app.dependency_overrides[dependency]
        app.dependency_overrides[dependency] = _audit_account_override
    return previous


def _restore_account_overrides(app, previous: dict[Any, Any]) -> None:
    session = _import_dashboard_session()
    if session is None:
        return

    for dependency_name in ("current_account", "optional_account"):
        dependency = getattr(session, dependency_name, None)
        if dependency is None:
            continue
        if dependency in previous:
            app.dependency_overrides[dependency] = previous[dependency]
        else:
            app.dependency_overrides.pop(dependency, None)


def run_api_audit(paths: list[str] | None = None) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from dashboard.app import app

    selected_paths = paths or SAFE_GET_PATHS
    endpoints: list[dict[str, Any]] = []

    previous_overrides = _install_account_overrides(app)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            for path in selected_paths:
                record: dict[str, Any] = {
                    "path": path,
                    "name": normalize_path_for_name(path),
                    "status_code": None,
                    "ok": False,
                    "json": False,
                    "findings": [],
                    "error": "",
                }
                try:
                    response = client.get(path)
                    record["status_code"] = response.status_code
                    is_json, payload, content_type = _response_payload(response)
                    record["json"] = is_json
                    record["ok"] = 200 <= response.status_code < 300 and is_json
                    if is_json:
                        record["findings"] = [
                            finding.to_dict() for finding in find_json_anomalies(payload)
                        ]
                    else:
                        record["error"] = (
                            f"non-json response: {content_type or 'unknown content type'}"
                        )
                except Exception as exc:  # pragma: no cover - defensive for unexpected runtime failures
                    record["error"] = f"{type(exc).__name__}: {exc}"
                endpoints.append(record)
    finally:
        _restore_account_overrides(app, previous_overrides)

    hard_finding_count = sum(
        1
        for endpoint in endpoints
        for finding in endpoint["findings"]
        if finding.get("severity") == "hard"
    )
    failed_endpoint_count = sum(1 for endpoint in endpoints if not endpoint["ok"] or endpoint["error"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "api",
        "total_endpoints": len(endpoints),
        "failed_endpoint_count": failed_endpoint_count,
        "hard_finding_count": hard_finding_count,
        "endpoints": endpoints,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit read-only dashboard API data health.")
    parser.add_argument("--output", default="test-results/data-display-audit/api-report.json")
    parser.add_argument("--path", action="append", dest="paths", help="Limit the scan to one path; repeatable.")
    parser.add_argument(
        "--fail-on-hard",
        action="store_true",
        help="Exit with status 1 when hard findings or endpoint failures exist.",
    )
    args = parser.parse_args(argv)

    report = run_api_audit(args.paths)
    output_path = Path(args.output)
    write_report(report, output_path)
    print(f"Wrote API data health report: {output_path}")
    print(
        f"Endpoints: {report['total_endpoints']}, failed: {report['failed_endpoint_count']}, "
        f"hard findings: {report['hard_finding_count']}"
    )
    if args.fail_on_hard and (report["failed_endpoint_count"] or report["hard_finding_count"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
