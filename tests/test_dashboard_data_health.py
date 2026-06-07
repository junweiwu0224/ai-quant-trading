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
    find_json_anomalies,
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
