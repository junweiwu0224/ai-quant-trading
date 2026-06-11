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

from data.storage.storage import DataStorage

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
    "/api/market/hotspot",
    "/api/market/northbound",
    "/api/valuation/health",
    "/api/datahub/health",
    "/api/datahub/decision-matrix?scope=codes&codes=600519&limit=3&fast=true",
    "/api/signals/health",
    "/api/signals/validation?top_n=5",
    "/api/signals/top?limit=5",
    "/api/signals/consistency?top_n=5",
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


def _payload_has(payload: dict[str, Any], field_path: str) -> bool:
    current: Any = payload
    for piece in field_path.split("."):
        if not isinstance(current, dict) or piece not in current:
            return False
        current = current[piece]
    return True


def _missing_metadata(field_path: str) -> AuditFinding:
    return AuditFinding(
        path=f"$.{field_path}",
        kind="missing_metadata",
        value=field_path,
        severity="soft",
    )


def _missing_degradation(value: str) -> AuditFinding:
    return AuditFinding(
        path="$.source_unavailable",
        kind="missing_degradation_metadata",
        value=value,
        severity="soft",
    )


def _add_missing_fields(
    findings: list[AuditFinding],
    payload: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    for field_path in fields:
        if not _payload_has(payload, field_path):
            findings.append(_missing_metadata(field_path))


def _add_item_missing_fields(
    findings: list[AuditFinding],
    item: dict[str, Any],
    index: int,
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        if field not in item:
            findings.append(_missing_metadata(f"items[{index}].{field}"))


def _has_degradation_context(payload: dict[str, Any]) -> bool:
    return any(
        bool(payload.get(key))
        for key in (
            "source_unavailable",
            "stale",
            "stale_reason",
            "partial_errors",
            "degradation_reason",
        )
    )


def find_metadata_findings(endpoint_path: str, payload: Any) -> list[AuditFinding]:
    """Find trust-context gaps for high-value read paths.

    These findings are intentionally soft: they flag ambiguous displays such as
    empty news or zero market counts without turning an offline data source into
    a hard test failure.
    """
    if not isinstance(payload, dict):
        return []

    parsed_path = urlsplit(endpoint_path).path
    findings: list[AuditFinding] = []

    if parsed_path == "/api/market/news":
        _add_missing_fields(
            findings,
            payload,
            ("source", "coverage_note", "timestamp"),
        )
        news = payload.get("news")
        sources = payload.get("sources")
        source_errors = payload.get("errors") or payload.get("partial_errors")
        if news == [] and (sources == [] or source_errors) and not _has_degradation_context(payload):
            findings.append(_missing_degradation("empty_news_requires_degradation_context"))
        return findings

    if parsed_path == "/api/market/radar":
        _add_missing_fields(
            findings,
            payload,
            ("source", "coverage_note", "total_stocks", "generated_at"),
        )
        if not _payload_has(payload, "universe"):
            findings.append(_missing_metadata("universe"))
        zero_total = payload.get("total_stocks") == 0
        if (payload.get("success") is False or zero_total) and not _has_degradation_context(payload):
            findings.append(_missing_degradation("empty_radar_requires_degradation_context"))
        return findings

    if parsed_path == "/api/market/breadth":
        _add_missing_fields(
            findings,
            payload,
            (
                "source",
                "universe",
                "coverage_note",
                "generated_at",
                "up_count",
                "down_count",
                "flat_count",
            ),
        )
        if not (_payload_has(payload, "effective_count") or _payload_has(payload, "latest_date_covered")):
            findings.append(_missing_metadata("effective_count"))
        zero_counts = all(payload.get(key) == 0 for key in ("up_count", "down_count", "flat_count"))
        if (payload.get("success") is False or zero_counts) and not _has_degradation_context(payload):
            findings.append(_missing_degradation("zero_breadth_requires_degradation_context"))
        return findings

    if parsed_path == "/api/market/heatmap":
        _add_missing_fields(
            findings,
            payload,
            ("source", "coverage_note", "generated_at", "sectors", "total", "fetched"),
        )
        if payload.get("sectors") == [] and not _has_degradation_context(payload):
            findings.append(_missing_degradation("empty_heatmap_requires_degradation_context"))
        return findings

    if parsed_path == "/api/market/hotspot":
        _add_missing_fields(
            findings,
            payload,
            ("source", "coverage_note", "generated_at", "timestamp", "summary"),
        )
        concepts = payload.get("concepts", payload.get("hot_concepts"))
        industries = payload.get("industries", payload.get("hot_industries"))
        empty_hotspot = concepts == [] and industries == [] and payload.get("fund_flow") == []
        if empty_hotspot and not _has_degradation_context(payload):
            findings.append(_missing_degradation("empty_hotspot_requires_degradation_context"))
        return findings

    if parsed_path == "/api/datahub/health":
        _add_missing_fields(
            findings,
            payload,
            (
                "source_health",
                "quality_summary",
                "quote",
                "stock_daily",
                "signal.provider",
                "signal.validation.confidence",
                "qlib",
                "full_daily_sync",
                "shadow",
                "providers",
            ),
        )
        return findings

    if parsed_path == "/api/datahub/decision-matrix":
        _add_missing_fields(
            findings,
            payload,
            (
                "summary.source_health",
                "summary.quality_summary",
                "summary.shadow",
                "summary.fast_mode",
                "summary.signal_status",
                "summary.signal_validation",
                "summary.signal_quality.confidence",
                "summary.generated_at",
            ),
        )
        items = payload.get("items")
        if isinstance(items, list):
            for index, item in enumerate(items[:5]):
                if not isinstance(item, dict):
                    findings.append(_missing_metadata(f"items[{index}]"))
                    continue
                _add_item_missing_fields(
                    findings,
                    item,
                    index,
                    (
                        "code",
                        "matrix_rank",
                        "decision_score",
                        "risk_level",
                        "primary_action",
                        "quote_source",
                        "signal_provider",
                        "signal_confidence",
                    ),
                )
        return findings

    if parsed_path == "/api/signals/health":
        _add_missing_fields(
            findings,
            payload,
            (
                "primary_collection",
                "runtime_boundary",
                "raw_source_role",
                "legacy_aliases.predictions",
                "legacy_adapters.qlib",
                "provider",
                "model_version",
                "raw_source",
                "fast_mode",
                "total",
                "validation.confidence",
                "validation.sample_days",
                "validation.provider",
            ),
        )
        return findings

    if parsed_path == "/api/signals/top":
        _add_missing_fields(
            findings,
            payload,
            (
                "primary_collection",
                "runtime_boundary",
                "raw_source_role",
                "raw_source",
                "provider",
                "model_version",
                "total",
                "signals",
                "predictions",
            ),
        )
        return findings

    if parsed_path == "/api/signals/validation":
        _add_missing_fields(findings, payload, ("provider", "confidence", "sample_days", "metrics.1d"))
        return findings

    if parsed_path == "/api/signals/consistency":
        _add_missing_fields(findings, payload, ("provider", "raw_source", "legacy_adapter"))
        return findings

    return findings


def find_stock_info_integrity_findings(audit: dict[str, Any]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    duplicate_plain_count = int(audit.get("duplicate_plain_count") or 0)
    duplicate_extra_row_count = int(audit.get("duplicate_extra_row_count") or 0)
    wrong_prefix_count = int(audit.get("wrong_prefix_count") or 0)
    legacy_plain_count = int(audit.get("legacy_plain_count") or 0)
    invalid_code_count = int(audit.get("invalid_code_count") or 0)
    blank_industry_count = int(audit.get("blank_industry_count") or 0)
    merged_blank_industry_count = int(audit.get("merged_blank_industry_count") or 0)

    if duplicate_plain_count:
        findings.append(
            AuditFinding(
                path="$.stock_info.duplicate_plain_count",
                kind="stock_info_integrity",
                value=(
                    f"duplicate_plain_count={duplicate_plain_count} "
                    f"extra_rows={duplicate_extra_row_count}"
                ),
                severity="soft",
            )
        )
    if wrong_prefix_count:
        findings.append(
            AuditFinding(
                path="$.stock_info.wrong_prefix_count",
                kind="stock_info_integrity",
                value=f"wrong_prefix_count={wrong_prefix_count}",
                severity="soft",
            )
        )
    if legacy_plain_count:
        findings.append(
            AuditFinding(
                path="$.stock_info.legacy_plain_count",
                kind="stock_info_integrity",
                value=f"legacy_plain_count={legacy_plain_count}",
                severity="soft",
            )
        )
    if invalid_code_count:
        findings.append(
            AuditFinding(
                path="$.stock_info.invalid_code_count",
                kind="stock_info_integrity",
                value=f"invalid_code_count={invalid_code_count}",
                severity="soft",
            )
        )
    if blank_industry_count or merged_blank_industry_count:
        findings.append(
            AuditFinding(
                path="$.stock_info.blank_industry_count",
                kind="stock_info_integrity",
                value=(
                    f"raw_blank_industry_count={blank_industry_count} "
                    f"merged_blank_industry_count={merged_blank_industry_count}"
                ),
                severity="soft",
            )
        )
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
    stock_info_integrity: dict[str, Any] = {}
    stock_info_cleanup_preview: dict[str, Any] = {}
    storage_findings: list[dict[str, str]] = []

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
                        if isinstance(payload, dict) and payload.get("success") is False:
                            record["ok"] = False
                            record["error"] = "business success=false"
                        record["findings"] = [
                            finding.to_dict()
                            for finding in (
                                find_json_anomalies(payload)
                                + find_metadata_findings(path, payload)
                            )
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

    try:
        storage = DataStorage()
        stock_info_integrity = storage.audit_stock_info_integrity()
        stock_info_cleanup_preview = storage.preview_stock_info_cleanup()
        storage_findings = [
            finding.to_dict() for finding in find_stock_info_integrity_findings(stock_info_integrity)
        ]
    except Exception as exc:  # pragma: no cover - defensive for local DB/runtime drift
        storage_findings = [
            AuditFinding(
                path="$.stock_info",
                kind="stock_info_integrity_audit_error",
                value=f"{type(exc).__name__}: {exc}",
                severity="soft",
            ).to_dict()
        ]

    hard_finding_count = sum(
        1
        for endpoint in endpoints
        for finding in endpoint["findings"]
        if finding.get("severity") == "hard"
    )
    soft_finding_count = sum(
        1
        for endpoint in endpoints
        for finding in endpoint["findings"]
        if finding.get("severity") == "soft"
    ) + sum(1 for finding in storage_findings if finding.get("severity") == "soft")
    failed_endpoint_count = sum(1 for endpoint in endpoints if not endpoint["ok"] or endpoint["error"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "api",
        "total_endpoints": len(endpoints),
        "failed_endpoint_count": failed_endpoint_count,
        "hard_finding_count": hard_finding_count,
        "soft_finding_count": soft_finding_count,
        "stock_info_integrity": stock_info_integrity,
        "stock_info_cleanup_preview": stock_info_cleanup_preview,
        "storage_findings": storage_findings,
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
        f"hard findings: {report['hard_finding_count']}, soft findings: {report['soft_finding_count']}"
    )
    if args.fail_on_hard and (report["failed_endpoint_count"] or report["hard_finding_count"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
