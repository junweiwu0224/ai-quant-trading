import json
import importlib
import sys
import types

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from scripts.dashboard_data_health import (
    HARD_BAD_STRINGS,
    SAFE_GET_PATHS,
    AuditFinding,
    find_stock_info_integrity_findings,
    find_json_anomalies,
    find_metadata_findings,
    normalize_path_for_name,
    run_api_audit,
)


PLAN_BASELINE_SAFE_GET_PATHS = [
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


def test_normalize_path_for_name_makes_stable_filename_piece():
    assert (
        normalize_path_for_name("/api/stock/kline/600519?period=daily&count=30")
        == "api_stock_kline_600519_period_daily_count_30"
    )


def test_find_json_anomalies_flags_hard_bad_strings_and_nonfinite_numbers():
    payload = {
        "quote": {
            "price": float("nan"),
            "change": "undefined",
            "rendered_change": "undefined%",
            "rendered_ratio": "NaN%",
            "rendered_limit": "Infinity%",
            "label": "[object Object]",
            "valid_placeholder": "--",
        },
        "items": [{"ratio": float("inf")}],
    }

    findings = find_json_anomalies(payload)
    rendered = {(item.path, item.kind, item.value) for item in findings}

    assert ("$.quote.price", "non_finite_number", "nan") in rendered
    assert ("$.quote.change", "bad_display_string", "undefined") in rendered
    assert ("$.quote.rendered_change", "bad_display_string", "undefined%") in rendered
    assert ("$.quote.rendered_ratio", "bad_display_string", "NaN%") in rendered
    assert ("$.quote.rendered_limit", "bad_display_string", "Infinity%") in rendered
    assert ("$.quote.label", "bad_display_string", "[object Object]") in rendered
    assert ("$.items[0].ratio", "non_finite_number", "inf") in rendered
    assert not any(item.path == "$.quote.valid_placeholder" for item in findings)


def test_audit_finding_is_json_serializable():
    finding = AuditFinding(path="$.x", kind="bad_display_string", value="nan", severity="hard")

    assert json.loads(json.dumps(finding.to_dict())) == {
        "path": "$.x",
        "kind": "bad_display_string",
        "value": "nan",
        "severity": "hard",
    }


def test_stock_info_integrity_findings_report_soft_metadata_risks():
    findings = find_stock_info_integrity_findings(
        {
            "duplicate_plain_count": 2,
            "duplicate_extra_row_count": 2,
            "wrong_prefix_count": 1,
            "legacy_plain_count": 1,
            "blank_industry_count": 40,
            "merged_blank_industry_count": 0,
        }
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert (
        "$.stock_info.duplicate_plain_count",
        "stock_info_integrity",
        "duplicate_plain_count=2 extra_rows=2",
        "soft",
    ) in rendered
    assert (
        "$.stock_info.wrong_prefix_count",
        "stock_info_integrity",
        "wrong_prefix_count=1",
        "soft",
    ) in rendered
    assert (
        "$.stock_info.legacy_plain_count",
        "stock_info_integrity",
        "legacy_plain_count=1",
        "soft",
    ) in rendered
    assert (
        "$.stock_info.blank_industry_count",
        "stock_info_integrity",
        "raw_blank_industry_count=40 merged_blank_industry_count=0",
        "soft",
    ) in rendered


def test_metadata_findings_warn_when_market_news_empty_lacks_trust_context():
    findings = find_metadata_findings(
        "/api/market/news",
        {
            "success": True,
            "timestamp": "2026-06-08T15:30:00",
            "news": [],
            "sources": [],
            "overall_sentiment": 0,
            "errors": ["no_news_source"],
        },
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert ("$.source", "missing_metadata", "source", "soft") in rendered
    assert ("$.coverage_note", "missing_metadata", "coverage_note", "soft") in rendered
    assert (
        "$.source_unavailable",
        "missing_degradation_metadata",
        "empty_news_requires_degradation_context",
        "soft",
    ) in rendered


def test_metadata_findings_warn_when_hotspot_empty_lacks_trust_context():
    findings = find_metadata_findings(
        "/api/market/hotspot",
        {
            "success": True,
            "summary": "暂无热点数据",
            "concepts": [],
            "industries": [],
            "fund_flow": [],
        },
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert ("$.source", "missing_metadata", "source", "soft") in rendered
    assert ("$.coverage_note", "missing_metadata", "coverage_note", "soft") in rendered
    assert ("$.generated_at", "missing_metadata", "generated_at", "soft") in rendered
    assert (
        "$.source_unavailable",
        "missing_degradation_metadata",
        "empty_hotspot_requires_degradation_context",
        "soft",
    ) in rendered


def test_run_api_audit_counts_soft_metadata_findings_without_failing_endpoint(monkeypatch):
    app = FastAPI()

    @app.get("/api/market/news")
    async def market_news():
        return {
            "success": True,
            "timestamp": "2026-06-08T15:30:00",
            "news": [],
            "sources": [],
            "overall_sentiment": 0,
            "errors": ["no_news_source"],
        }

    _install_fake_dashboard_app(monkeypatch, app)

    report = run_api_audit(["/api/market/news"])
    endpoint = report["endpoints"][0]

    assert endpoint["ok"] is True
    assert report["failed_endpoint_count"] == 0
    assert report["hard_finding_count"] == 0
    assert report["soft_finding_count"] >= 3
    assert any(finding["kind"] == "missing_metadata" for finding in endpoint["findings"])


def test_run_api_audit_includes_stock_info_integrity_soft_findings(monkeypatch):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"success": True}

    class FakeStorage:
        def audit_stock_info_integrity(self, sample_limit=20):
            return {
                "duplicate_plain_count": 1,
                "duplicate_extra_row_count": 1,
                "wrong_prefix_count": 1,
                "legacy_plain_count": 0,
                "blank_industry_count": 1,
                "merged_blank_industry_count": 0,
            }

        def preview_stock_info_cleanup(self, sample_limit=20):
            return {
                "mode": "preview_only",
                "scope": "wrong_prefix_duplicates",
                "candidate_count": 1,
                "cleanup_ready_count": 1,
                "merge_required_count": 0,
                "skipped_no_canonical_count": 0,
                "candidates": [],
            }

    _install_fake_dashboard_app(monkeypatch, app)
    monkeypatch.setattr(
        "scripts.dashboard_data_health.DataStorage",
        lambda: FakeStorage(),
        raising=False,
    )

    report = run_api_audit(["/health"])

    assert report["failed_endpoint_count"] == 0
    assert report["stock_info_integrity"]["wrong_prefix_count"] == 1
    assert report["stock_info_cleanup_preview"]["candidate_count"] == 1
    assert any(
        finding["path"] == "$.stock_info.wrong_prefix_count"
        for finding in report["storage_findings"]
    )
    assert report["soft_finding_count"] >= 3


def test_metadata_findings_warn_when_decision_matrix_items_lack_trust_context():
    findings = find_metadata_findings(
        "/api/datahub/decision-matrix?scope=codes&codes=600519&limit=3&fast=true",
        {
            "success": True,
            "items": [
                {
                    "code": "600519",
                    "matrix_rank": 1,
                    "decision_score": 72,
                    "name": "贵州茅台",
                }
            ],
            "summary": {
                "source_health": {},
                "quality_summary": {},
                "shadow": {},
                "fast_mode": True,
                "signal_status": "stale",
                "signal_validation": {},
                "signal_quality": {"confidence": "unverified"},
                "generated_at": "2026-06-08T15:50:00",
            },
        },
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert ("$.items[0].quote_source", "missing_metadata", "items[0].quote_source", "soft") in rendered
    assert (
        "$.items[0].signal_provider",
        "missing_metadata",
        "items[0].signal_provider",
        "soft",
    ) in rendered
    assert ("$.items[0].risk_level", "missing_metadata", "items[0].risk_level", "soft") in rendered
    assert (
        "$.items[0].primary_action",
        "missing_metadata",
        "items[0].primary_action",
        "soft",
    ) in rendered


def test_metadata_findings_warn_when_signal_health_lacks_validation_evidence():
    findings = find_metadata_findings(
        "/api/signals/health?fast=true",
        {
            "success": True,
            "status": "online",
            "primary_collection": "signals",
            "runtime_boundary": "signals",
            "raw_source_role": "legacy_cache",
            "legacy_aliases": {"predictions": "signals"},
            "legacy_adapters": {"qlib": "/api/qlib/health"},
            "provider": "local_momentum",
            "model_version": "local_momentum_v1",
            "raw_source": "legacy_qlib",
            "fast_mode": True,
            "total": 5197,
        },
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert (
        "$.validation.confidence",
        "missing_metadata",
        "validation.confidence",
        "soft",
    ) in rendered
    assert (
        "$.validation.sample_days",
        "missing_metadata",
        "validation.sample_days",
        "soft",
    ) in rendered


def test_metadata_findings_warn_when_signal_validation_lacks_core_evidence():
    findings = find_metadata_findings(
        "/api/signals/validation?top_n=5",
        {
            "success": True,
            "confidence": "validated_positive",
        },
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert ("$.provider", "missing_metadata", "provider", "soft") in rendered
    assert ("$.sample_days", "missing_metadata", "sample_days", "soft") in rendered
    assert ("$.metrics.1d", "missing_metadata", "metrics.1d", "soft") in rendered


def test_safe_get_paths_cover_user_selected_data_areas():
    assert SAFE_GET_PATHS == PLAN_BASELINE_SAFE_GET_PATHS
    assert all("{" not in path and "}" not in path for path in SAFE_GET_PATHS)
    assert all(not path.startswith("/api/account/") for path in SAFE_GET_PATHS)


def _install_fake_dashboard_app(monkeypatch, app: FastAPI) -> None:
    app_module = types.ModuleType("dashboard.app")
    app_module.app = app
    monkeypatch.setitem(sys.modules, "dashboard.app", app_module)


def test_run_api_audit_installs_test_account_overrides_before_client_creation(monkeypatch):
    app = FastAPI()
    session_module = types.ModuleType("dashboard.session")

    async def optional_account():
        return None

    async def current_account():
        raise HTTPException(status_code=401, detail="login required")

    session_module.optional_account = optional_account
    session_module.current_account = current_account
    monkeypatch.setitem(sys.modules, "dashboard.session", session_module)

    @app.get("/needs-current")
    async def needs_current(account: dict = Depends(current_account)):
        return {
            "user_id": account["id"],
            "workspace_id": account["workspace"]["id"],
            "read_market": account["permissions"]["read_market"],
        }

    @app.get("/needs-optional")
    async def needs_optional(account: dict | None = Depends(optional_account)):
        if not account:
            raise HTTPException(status_code=401, detail="login required")
        return {
            "user_id": account["id"],
            "workspace_id": account["workspace"]["id"],
            "read_market": account["permissions"]["read_market"],
        }

    _install_fake_dashboard_app(monkeypatch, app)

    report = run_api_audit(["/needs-current", "/needs-optional"])

    assert report["failed_endpoint_count"] == 0
    assert [endpoint["status_code"] for endpoint in report["endpoints"]] == [200, 200]
    assert all(endpoint["ok"] for endpoint in report["endpoints"])
    assert all(endpoint["json"] for endpoint in report["endpoints"])


def test_run_api_audit_skips_account_overrides_when_dashboard_session_missing(monkeypatch):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    _install_fake_dashboard_app(monkeypatch, app)
    monkeypatch.delitem(sys.modules, "dashboard.session", raising=False)

    real_import_module = importlib.import_module

    def import_module(name, package=None):
        if name == "dashboard.session":
            raise ModuleNotFoundError(
                "No module named 'dashboard.session'", name="dashboard.session"
            )
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", import_module)

    report = run_api_audit(["/health"])
    endpoint = report["endpoints"][0]

    assert endpoint["path"] == "/health"
    assert endpoint["status_code"] == 200
    assert endpoint["ok"] is True
    assert endpoint["json"] is True
    assert report["failed_endpoint_count"] == 0


def test_run_api_audit_counts_2xx_non_json_responses_as_failed(monkeypatch):
    app = FastAPI()

    @app.get("/plain")
    async def plain():
        return PlainTextResponse("healthy")

    _install_fake_dashboard_app(monkeypatch, app)

    report = run_api_audit(["/plain"])
    endpoint = report["endpoints"][0]

    assert endpoint["status_code"] == 200
    assert endpoint["ok"] is False
    assert endpoint["json"] is False
    assert endpoint["error"].startswith("non-json response:")
    assert report["failed_endpoint_count"] == 1


def test_run_api_audit_counts_success_false_json_responses_as_failed(monkeypatch):
    app = FastAPI()

    @app.get("/business-failed")
    async def business_failed():
        return {"success": False, "error": "upstream unavailable"}

    _install_fake_dashboard_app(monkeypatch, app)

    report = run_api_audit(["/business-failed"])
    endpoint = report["endpoints"][0]

    assert endpoint["status_code"] == 200
    assert endpoint["json"] is True
    assert endpoint["ok"] is False
    assert endpoint["error"] == "business success=false"
    assert report["failed_endpoint_count"] == 1
