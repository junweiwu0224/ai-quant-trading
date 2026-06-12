from __future__ import annotations

import sys
import types

import pandas as pd

from alpha import iwencai_client


def test_iwencai_status_reports_missing_provider_without_breaking_legacy(monkeypatch):
    monkeypatch.setitem(sys.modules, "pywencai", None)
    monkeypatch.setattr(iwencai_client, "_last_query_time", 0.0)

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(iwencai_client.asyncio, "sleep", fake_sleep)

    result = iwencai_client.asyncio.run(iwencai_client.query_iwencai_with_status("高股息"))
    legacy_df = iwencai_client.asyncio.run(iwencai_client.query_iwencai("高股息"))

    assert result.data.empty
    assert result.provider_status == "provider_unavailable"
    assert result.failure_type == "provider_unavailable"
    assert "pywencai" in result.failure_reason
    assert isinstance(legacy_df, pd.DataFrame)
    assert legacy_df.empty


def test_iwencai_status_classifies_invalid_provider_response(monkeypatch):
    fake_pywencai = types.SimpleNamespace(get=lambda **_kwargs: {"unexpected": "shape"})
    monkeypatch.setitem(sys.modules, "pywencai", fake_pywencai)
    monkeypatch.setattr(iwencai_client, "_last_query_time", 0.0)

    result = iwencai_client.asyncio.run(iwencai_client.query_iwencai_with_status("高股息"))

    assert result.data.empty
    assert result.provider_status == "invalid_provider_response"
    assert result.failure_type == "invalid_provider_response"
    assert result.response_type == "dict"


def test_iwencai_status_classifies_rate_limit_exception(monkeypatch):
    def raise_rate_limit(**_kwargs):
        raise RuntimeError("429 too many requests")

    fake_pywencai = types.SimpleNamespace(get=raise_rate_limit)
    monkeypatch.setitem(sys.modules, "pywencai", fake_pywencai)
    monkeypatch.setattr(iwencai_client, "_last_query_time", 0.0)

    result = iwencai_client.asyncio.run(iwencai_client.query_iwencai_with_status("高股息"))

    assert result.data.empty
    assert result.provider_status == "rate_limited"
    assert result.failure_type == "rate_limited"
    assert result.retry_after_seconds == iwencai_client._MIN_INTERVAL


def test_iwencai_status_classifies_unsupported_field_exception(monkeypatch):
    def raise_unsupported_field(**_kwargs):
        raise RuntimeError("unknown field: ESG评分 unsupported")

    fake_pywencai = types.SimpleNamespace(get=raise_unsupported_field)
    monkeypatch.setitem(sys.modules, "pywencai", fake_pywencai)
    monkeypatch.setattr(iwencai_client, "_last_query_time", 0.0)

    result = iwencai_client.asyncio.run(iwencai_client.query_iwencai_with_status("ESG评分大于80"))

    assert result.data.empty
    assert result.provider_status == "ok"
    assert result.failure_type == "unsupported_field"
    assert "字段" in result.failure_reason


def test_iwencai_status_classifies_schema_drift_exception(monkeypatch):
    def raise_schema_drift(**_kwargs):
        raise RuntimeError("schema drift: column mapping changed")

    fake_pywencai = types.SimpleNamespace(get=raise_schema_drift)
    monkeypatch.setitem(sys.modules, "pywencai", fake_pywencai)
    monkeypatch.setattr(iwencai_client, "_last_query_time", 0.0)

    result = iwencai_client.asyncio.run(iwencai_client.query_iwencai_with_status("高股息"))

    assert result.data.empty
    assert result.provider_status == "schema_drift"
    assert result.failure_type == "schema_drift"
    assert "字段结构" in result.failure_reason
