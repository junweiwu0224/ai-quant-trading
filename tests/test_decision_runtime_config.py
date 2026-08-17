from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import decision.runtime as runtime_module
from decision.runtime import DecisionRuntime


class _EmptyFrame:
    empty = True


class _Store:
    def __init__(self, version: dict[str, Any]) -> None:
        self.version = version
        self.saved_eligibility: tuple[dict[str, Any], list[str]] | None = None

    def get_current_version(self, _workspace_id: str, _portfolio_id: str) -> dict[str, Any]:
        return self.version

    def create_version(self, _workspace_id: str, _portfolio_id: str, _config: dict[str, Any]) -> dict[str, Any]:
        return self.version

    def get_portfolio(self, _workspace_id: str, _portfolio_id: str) -> dict[str, Any]:
        return {"id": "portfolio-1", "market": "CN"}

    def list_members(self, _workspace_id: str, _portfolio_id: str) -> list[dict[str, Any]]:
        return [{"id": "membership-1", "symbol": "600519", "name": "测试标的"}]

    def create_snapshot(self, _workspace_id: str, _version_id: str, payload: dict[str, Any], _source: str, _quality_status: str) -> dict[str, Any]:
        return {"id": "snapshot-1", "payload": payload}

    def list_reports(self, _workspace_id: str, _portfolio_id: str, *, limit: int) -> list[dict[str, Any]]:
        return []

    def latest_report(self, _workspace_id: str, _portfolio_id: str, _report_type: str, *, portfolio_version_id: str | None = None) -> dict[str, Any] | None:
        return None

    def list_targets(self, _workspace_id: str) -> list[dict[str, Any]]:
        return []

    def list_routes(self, _workspace_id: str, _portfolio_id: str) -> list[dict[str, Any]]:
        return []

    def save_eligibility(self, _version_id: str, checks: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        self.saved_eligibility = checks, reasons
        return {"checks": checks, "reasons": reasons}


class _Storage:
    def get_stock_daily(self, _symbol: str) -> _EmptyFrame:
        return _EmptyFrame()


def _runtime(config: dict[str, Any]) -> DecisionRuntime:
    version = {
        "id": "version-1",
        "config": {
            "strategies": [{"strategy_name": "momentum", "enabled": True, "weight": 1}],
            **config,
        },
    }
    return DecisionRuntime(_Store(version), _Storage())


def _stub_validation(captured: dict[str, Any]):
    def validate(*_args: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            as_dict=lambda: {
                "passed": True,
                "reasons": [],
                "lookahead_safe": True,
                "windows": [],
            }
        )

    return validate


def test_validate_uses_historical_defaults_when_validation_config_is_missing(monkeypatch):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(runtime_module, "walk_forward_validate", _stub_validation(captured))

    result = _runtime({}).validate("workspace-1", "portfolio-1")

    expected = {
        "calendar": "SSE/SZSE",
        "cost_model_version": "generic-assumption-v1",
        "cost_bps": 10.0,
        "min_history_months": 54,
        "train_months": 24,
        "out_of_sample_months": 6,
        "step_months": 6,
        "required_windows": 3,
        "max_drawdown_limit": 0.25,
        "annualized_turnover_limit": 12.0,
        "annualization_days": 252,
        "survivorship_bias_control": False,
        "universe_snapshot_ref": None,
    }
    assert {key: captured[key] for key in expected} == expected
    assert captured["execution_contract"]["execution_rule"] == "signal_at_close_then_next_tradable_bar_open"
    assert captured["execution_contract"]["benchmark_value_field"] == "total_return_index"
    assert captured["benchmark_history"] is None
    assert result["validation_config_valid"] is True
    assert result["validation_config_issues"] == []
    assert result["passed"] is True


def test_validate_falls_back_from_invalid_and_extreme_numbers_but_blocks_validation(monkeypatch):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(runtime_module, "walk_forward_validate", _stub_validation(captured))

    result = _runtime(
        {
            "validation": {
                "cost_bps": float("nan"),
                "min_history_months": 10**100,
                "train_months": "not-an-int",
                "out_of_sample_months": 0,
                "step_months": -6,
                "required_windows": float("inf"),
                "max_drawdown": 2.0,
                "max_annualized_turnover": 10**100,
            }
        }
    ).validate("workspace-1", "portfolio-1")

    assert captured["cost_bps"] == 10.0
    assert captured["min_history_months"] == 54
    assert captured["train_months"] == 24
    assert captured["out_of_sample_months"] == 6
    assert captured["step_months"] == 6
    assert captured["required_windows"] == 3
    assert captured["max_drawdown_limit"] == 0.25
    assert captured["annualized_turnover_limit"] == 12.0

    fields = {item["field"] for item in result["validation_config_issues"]}
    assert fields == {
        "cost_bps",
        "min_history_months",
        "train_months",
        "out_of_sample_months",
        "step_months",
        "required_windows",
        "max_drawdown",
        "max_annualized_turnover",
    }
    assert result["validation_config_valid"] is False
    assert result["passed"] is False
    assert "validation_config_invalid" in result["reasons"]
    assert "validation_config_invalid:cost_bps" in result["reasons"]


def test_eligibility_blocks_a_version_with_invalid_validation_config(monkeypatch):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(runtime_module, "walk_forward_validate", _stub_validation(captured))

    result = _runtime({"validation": {"max_drawdown": "NaN"}}).eligibility("workspace-1", "portfolio-1")

    assert result["eligible"] is False
    assert result["checks"]["validation_ok"] is False
    assert "validation_config_invalid" in result["reasons"]
    assert "validation_config_invalid:max_drawdown" in result["reasons"]
    assert result["validation"]["passed"] is False
