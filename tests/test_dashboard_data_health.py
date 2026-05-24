import json

from scripts.dashboard_data_health import (
    HARD_BAD_STRINGS,
    SAFE_GET_PATHS,
    AuditFinding,
    find_json_anomalies,
    normalize_path_for_name,
)


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
            "label": "[object Object]",
            "valid_placeholder": "--",
        },
        "items": [{"ratio": float("inf")}],
    }

    findings = find_json_anomalies(payload)
    rendered = {(item.path, item.kind, item.value) for item in findings}

    assert ("$.quote.price", "non_finite_number", "nan") in rendered
    assert ("$.quote.change", "bad_display_string", "undefined") in rendered
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
    expected = {
        "/api/stock/detail/600519",
        "/api/stock/kline/600519?period=daily&count=30",
        "/api/stock/market/indices",
        "/api/market/radar",
        "/api/portfolio/snapshot",
        "/api/paper/status",
        "/api/backtest/strategies",
        "/api/alpha/model-status",
        "/api/watchlist",
        "/api/datahub/health",
    }

    assert expected.issubset(set(SAFE_GET_PATHS))
    assert all("{" not in path and "}" not in path for path in SAFE_GET_PATHS)
    assert all(not path.startswith("/api/account/") for path in SAFE_GET_PATHS)
