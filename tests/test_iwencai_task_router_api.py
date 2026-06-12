from __future__ import annotations

import sys
import types

import pandas as pd


def _install_fake_iwencai(monkeypatch, df: pd.DataFrame) -> None:
    module = types.ModuleType("alpha.iwencai_client")

    async def fake_query_iwencai(query: str, cookie: str = "") -> pd.DataFrame:
        assert query
        assert cookie == ""
        return df.copy()

    module.query_iwencai = fake_query_iwencai
    monkeypatch.setitem(sys.modules, "alpha.iwencai_client", module)
    if "alpha" in sys.modules:
        monkeypatch.setattr(sys.modules["alpha"], "iwencai_client", module, raising=False)


def _install_fake_iwencai_result(monkeypatch, result) -> None:
    module = types.ModuleType("alpha.iwencai_client")

    async def fake_query_iwencai_with_status(query: str, cookie: str = ""):
        assert query
        assert cookie == ""
        return result

    async def fake_query_iwencai(query: str, cookie: str = "") -> pd.DataFrame:
        data = result.get("data") if isinstance(result, dict) else getattr(result, "data", pd.DataFrame())
        return data.copy()

    module.query_iwencai_with_status = fake_query_iwencai_with_status
    module.query_iwencai = fake_query_iwencai
    monkeypatch.setitem(sys.modules, "alpha.iwencai_client", module)
    if "alpha" in sys.modules:
        monkeypatch.setattr(sys.modules["alpha"], "iwencai_client", module, raising=False)


def _action_ids(body: dict) -> set[str]:
    return {item["id"] for item in body["actions"]}


def _assert_read_only_iwencai_actions(body: dict, *, has_candidates: bool) -> None:
    action_ids = _action_ids(body)
    assert "analyze" in action_ids
    assert "ask_ai" in action_ids
    assert ("open_stock" in action_ids) is True
    open_action = next(item for item in body["actions"] if item["id"] == "open_stock")
    assert open_action["enabled"] is has_candidates
    assert "send_screener" not in action_ids
    assert "add_watchlist" not in action_ids
    assert "create_basket" not in action_ids
    assert "draft_backtest" not in action_ids


def test_iwencai_api_returns_backend_owned_task_router_schema(client, monkeypatch):
    _install_fake_iwencai(
        monkeypatch,
        pd.DataFrame(
            [
                {
                    "股票代码": "600000.SH",
                    "股票简称": "浦发银行",
                    "最新价": 8.5,
                    "最新涨跌幅": 1.2,
                    "所属同花顺行业": "银行-股份制银行",
                    "所属概念": "高股息;低估值",
                    "股息率": 5.1,
                },
                {
                    "股票代码": "000001.SZ",
                    "股票简称": "平安银行",
                    "最新价": 10.2,
                    "最新涨跌幅": -0.3,
                    "所属同花顺行业": "银行-股份制银行",
                    "所属概念": "低估值",
                    "股息率": 3.2,
                },
            ]
        ),
    )

    resp = client.post(
        "/api/llm/iwencai",
        json={
            "query": "高股息 低估值 近5日放量",
            "source_context": {
                "source": "global_search",
                "result_pool_id": "global-search:test",
                "cookie": "SHOULD_NOT_LEAK",
                "authorization": "Bearer SHOULD_NOT_LEAK",
                "headers": {"x-token": "SHOULD_NOT_LEAK"},
                "concept": "token=SHOULD_NOT_LEAK",
                "rank_reason": "token=SHOULD_NOT_LEAK",
                "parsed_conditions": [
                    {
                        "raw_text": "高股息",
                        "nested": {
                            "deeper": {
                                "note": "cookie=SHOULD_NOT_LEAK token=SHOULD_NOT_LEAK",
                            },
                        },
                    },
                ],
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["schema_version"] == "iwencai_task_router_v1"
    assert body["status"] == "partial_result"
    assert body["total"] == 2
    assert len(body["data"]) == 2
    assert body["intent"]["type"] == "natural_language_screener"
    assert body["intent"]["confidence"] >= 0.7
    assert [item["raw_text"] for item in body["parsed_conditions"]][:3] == ["高股息", "低估值", "近5日放量"]
    assert body["parsed_conditions"][0]["field"] == "股息率"
    assert body["parsed_conditions"][0]["hit_count"] == 2
    assert body["parsed_conditions"][0]["hit_count_status"] == "verified"
    assert body["parsed_conditions"][0]["source_field"] == "股息率"
    assert body["parsed_conditions"][0]["evidence"]["evidence_level"] == "provider_field"
    assert body["parsed_conditions"][2]["window"] == "5d"
    assert body["parsed_conditions"][2]["hit_count"] is None
    assert body["parsed_conditions"][2]["hit_count_status"] == "missing_source_field"
    assert body["parsed_conditions"][2]["missing_reason"]
    assert body["status"] == "partial_result"
    assert body["selected_bucket"] == "candidates"
    assert body["buckets"][0]["id"] == "candidates"
    assert body["buckets"][0]["count"] == 2
    assert body["buckets"][0]["items"][0]["code"] == "600000"
    assert body["buckets"][1]["id"] == "themes"
    assert not any(action["id"] == "create_basket" for action in body["actions"])
    assert not any(action["id"] == "draft_backtest" for action in body["actions"])
    assert body["source_status"]["status"] == "partial_source_failure"
    assert body["source_status"]["type"] == "partial_source_failure"
    assert body["source_context"]["source"] == "global_search"
    assert body["source_context"]["context_type"] == "iwencai"
    assert body["source_context"]["result_pool_id"].startswith("iwencai:")
    assert body["source_context"]["origin_result_pool_id"] == "global-search:test"
    assert body["source_context"]["origin_context"]["result_pool_id"] == "global-search:test"
    assert body["source_context"]["intent_type"] == "natural_language_screener"
    assert body["source_context"]["selected_bucket"] == "candidates"
    assert body["source_context"]["condition_hit_count"]["高股息"] == 2
    assert body["source_context"]["condition_hit_count"]["近5日放量"] is None
    assert body["source_context"]["condition_evidence"]["近5日放量"]["hit_count_status"] == "missing_source_field"
    assert "cookie" not in body["source_context"]
    assert "authorization" not in body["source_context"]
    assert "headers" not in body["source_context"]
    assert "SHOULD_NOT_LEAK" not in str(body["source_context"])
    assert body["source_context"]["concept"] == "[redacted]"
    assert "cookie=" not in str(body["source_context"]["origin_context"])
    assert "token=" not in str(body["source_context"]["origin_context"])
    assert body["source_context"]["rank_reason"] == "问财条件: 高股息 / 低估值 / 近5日放量"
    assert body["source_status"]["provider"] == "iwencai"
    assert body["source_status"]["status"] == "partial_source_failure"


def test_iwencai_api_keeps_router_schema_for_empty_result(client, monkeypatch):
    _install_fake_iwencai(monkeypatch, pd.DataFrame())

    resp = client.post("/api/llm/iwencai", json={"query": "高股息"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == []
    assert body["total"] == 0
    assert body["status"] == "no_match"
    assert body["failure_type"] == "no_match"
    assert body["parsed_conditions"][0]["hit_count"] == 0
    assert body["parsed_conditions"][0]["hit_count_status"] == "provider_empty_result"
    assert body["parsed_conditions"][0]["status"] == "no_match"
    assert body["intent"]["type"] == "natural_language_screener"
    assert body["buckets"][0]["id"] == "candidates"
    assert body["buckets"][0]["status"] == "no_match"
    assert body["source_context"]["status_reason"]
    assert body["source_context"]["next_action"]
    assert "open_stock" in [item["id"] for item in body["actions"]]
    assert "create_basket" not in [item["id"] for item in body["actions"]]


def test_iwencai_api_field_evidence_missing_does_not_fabricate_hit_count(client, monkeypatch):
    _install_fake_iwencai(
        monkeypatch,
        pd.DataFrame(
            [
                {"股票代码": "600000.SH", "股票简称": "浦发银行", "最新价": 8.5},
                {"股票代码": "000001.SZ", "股票简称": "平安银行", "最新价": 10.2},
            ]
        ),
    )

    resp = client.post(
        "/api/llm/iwencai",
        json={
            "query": "高股息 低估值",
            "source_context": {
                "source": "global_search",
                "parsed_conditions": [{"raw_text": "高股息", "hit_count": 999999}],
                "condition_hit_count": {"高股息": 999999},
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "partial_result"
    assert body["source_status"]["status"] == "partial_source_failure"
    assert body["source_context"]["origin_context"]["condition_hit_count"]["高股息"] == 999999
    for condition in body["parsed_conditions"]:
        assert condition["hit_count"] is None
        assert condition["hit_count_status"] == "missing_source_field"
        assert condition["evidence"]["hit_count"] is None
        assert condition["evidence"]["evidence_level"] == "none"
        assert condition["missing_reason"] == "结果字段中缺少可验证该条件的来源字段"
        assert condition["status"] == "degraded_data"
    assert body["source_context"]["condition_hit_count"]["高股息"] is None
    assert body["source_context"]["condition_evidence"]["高股息"]["hit_count_status"] == "missing_source_field"
    action_ids = [item["id"] for item in body["actions"]]
    assert "open_stock" in action_ids
    assert "analyze" in action_ids
    assert "create_basket" not in action_ids
    assert "draft_backtest" not in action_ids


def test_iwencai_api_returns_candidate_row_provenance(client, monkeypatch):
    _install_fake_iwencai(
        monkeypatch,
        pd.DataFrame(
            [
                {
                    "股票代码": "600000.SH",
                    "股票简称": "浦发银行",
                    "最新价": 8.5,
                    "所属同花顺行业": "银行-股份制银行",
                    "股息率": 5.1,
                    "市盈率": 5.2,
                    "量比": 1.8,
                },
                {
                    "股票代码": "000001.SZ",
                    "股票简称": "平安银行",
                    "最新价": 10.2,
                    "所属同花顺行业": "银行-股份制银行",
                    "股息率": "",
                    "市盈率": 6.3,
                    "量比": 1.5,
                },
            ]
        ),
    )

    resp = client.post(
        "/api/llm/iwencai",
        json={
            "query": "高股息 低估值 放量",
            "source_context": {
                "source": "global_search",
                "result_pool_id": "global-search:row-provenance",
                "candidate_provenance": {"validation_status": "verified"},
                "candidate_codes": ["999999"],
                "code": "999999",
                "name": "伪造股票",
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "partial_result"
    assert body["source_status"]["status"] == "partial_source_failure"
    candidates = body["buckets"][0]["items"]
    assert [item["code"] for item in candidates] == ["600000", "000001"]

    first = candidates[0]["candidate_provenance"]
    assert first["result_pool_id"].startswith("iwencai:")
    assert first["row_id"].startswith(f"{first['result_pool_id']}:row:")
    assert "global-search:row-provenance" not in first["row_id"]
    assert first["code"] == "600000"
    assert first["rank"] == 1
    assert first["validation_status"] == "verified"
    assert first["evidence_level"] == "provider_field"
    assert {item["raw_text"] for item in first["matched_conditions"]} == {"高股息", "低估值", "放量"}
    assert {item["source_field"] for item in first["matched_conditions"]} >= {"股息率", "市盈率", "量比"}
    assert first["missing_conditions"] == []
    assert first["raw_field_map"]["股票代码"] == "600000.SH"
    assert first["raw_field_map"]["股票简称"] == "浦发银行"
    assert "candidate_provenance" not in first["raw_field_map"]
    assert "999999" not in str(first)
    assert "伪造股票" not in str(first)

    second = candidates[1]["candidate_provenance"]
    assert second["code"] == "000001"
    assert second["rank"] == 2
    assert second["validation_status"] == "partial"
    assert second["evidence_level"] == "partial_provider_field"
    assert {item["raw_text"] for item in second["matched_conditions"]} == {"低估值", "放量"}
    assert second["missing_conditions"][0]["raw_text"] == "高股息"
    assert second["missing_conditions"][0]["hit_count_status"] == "missing_row_value"
    assert "该候选行缺少可验证的条件字段取值" in second["missing_reason"]
    assert "create_basket" not in [item["id"] for item in body["actions"]]
    assert "draft_backtest" not in [item["id"] for item in body["actions"]]


def test_iwencai_api_distinguishes_provider_empty_from_unavailable(client, monkeypatch):
    _install_fake_iwencai_result(
        monkeypatch,
        {
            "data": pd.DataFrame(),
            "provider": "iwencai",
            "provider_status": "provider_unavailable",
            "failure_type": "provider_unavailable",
            "failure_reason": "pywencai 未安装，问财查询不可用",
            "response_type": "import_error",
            "data_as_of": "2026-06-10T10:00:00+00:00",
            "cache_status": "live_request",
        },
    )

    resp = client.post("/api/llm/iwencai", json={"query": "高股息 低估值 近5日放量"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["data"] == []
    assert body["total"] == 0
    assert body["status"] == "failed"
    assert body["failure_type"] == "provider_unavailable"
    assert body["failure_reason"] == "pywencai 未安装，问财查询不可用"
    assert body["source_status"]["status"] == "unavailable"
    assert body["source_status"]["provider_status"] == "provider_unavailable"
    assert body["source_status"]["type"] == "provider_unavailable"
    assert body["source_status"]["response_type"] == "import_error"
    assert body["source_context"]["data_status"] == "unavailable"
    assert body["source_context"]["failure_type"] == "provider_unavailable"
    assert body["source_context"]["status_reason"] == "pywencai 未安装，问财查询不可用"
    assert body["parsed_conditions"][0]["hit_count"] is None
    assert body["parsed_conditions"][0]["hit_count_status"] == "source_unavailable"
    assert body["parsed_conditions"][0]["status"] == "failed"
    action_ids = [item["id"] for item in body["actions"]]
    assert "analyze" in action_ids
    assert "ask_ai" in action_ids
    assert "create_basket" not in action_ids
    assert "draft_backtest" not in action_ids
    assert "send_screener" not in action_ids
    assert "no_match" != body["failure_type"]


def test_iwencai_api_maps_provider_failure_statuses(client, monkeypatch):
    cases = [
        ("request_failed", "failed", "request_failed", "问财查询失败，请稍后重试"),
        ("rate_limited", "rate_limited", "rate_limited", "问财源限流或访问频率受限，请稍后重试"),
        ("invalid_provider_response", "invalid_response", "invalid_provider_response", "问财返回格式异常，无法稳定解析为候选池"),
    ]

    for provider_status, source_status, failure_type, reason in cases:
        _install_fake_iwencai_result(
            monkeypatch,
            {
                "data": pd.DataFrame(),
                "provider": "iwencai",
                "provider_status": provider_status,
                "failure_type": failure_type,
                "failure_reason": reason,
                "response_type": "FakeResponse",
                "retry_after_seconds": 12 if provider_status == "rate_limited" else None,
                "data_as_of": "2026-06-10T10:00:00+00:00",
                "cache_status": "live_request",
            },
        )

        resp = client.post("/api/llm/iwencai", json={"query": f"case {provider_status}"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["status"] == "failed"
        assert body["failure_type"] == failure_type
        assert body["failure_reason"] == reason
        assert body["source_status"]["status"] == source_status
        assert body["source_status"]["provider_status"] == provider_status
        assert body["source_status"]["type"] == failure_type
        assert body["source_context"]["data_status"] == source_status
        assert body["source_context"]["failure_type"] == failure_type
        assert body["source_context"]["status_reason"] == reason
        assert "create_basket" not in [item["id"] for item in body["actions"]]
        if provider_status == "rate_limited":
            assert body["source_status"]["retry_after_seconds"] == 12


def test_iwencai_api_degrades_stale_cache_without_write_actions(client, monkeypatch):
    _install_fake_iwencai_result(
        monkeypatch,
        {
            "data": pd.DataFrame(
                [
                    {
                        "股票代码": "600000.SH",
                        "股票简称": "浦发银行",
                        "股息率": 5.1,
                        "市盈率": 5.2,
                    },
                    {
                        "股票代码": "000001.SZ",
                        "股票简称": "平安银行",
                        "股息率": 3.2,
                        "市盈率": 6.3,
                    },
                ]
            ),
            "provider": "iwencai",
            "provider_status": "ok",
            "failure_type": "stale_cache",
            "failure_reason": "当前结果来自旧缓存，需刷新后再执行写入动作",
            "response_type": "DataFrame",
            "data_as_of": "2026-06-09T10:00:00+00:00",
            "cache_status": "stale_cache",
        },
    )

    resp = client.post("/api/llm/iwencai", json={"query": "高股息 低估值"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "degraded_data"
    assert body["failure_type"] == "stale_cache"
    assert body["total"] == 2
    assert [item["股票代码"] for item in body["data"]] == ["600000.SH", "000001.SZ"]
    assert body["source_status"]["status"] == "stale_cache"
    assert body["source_status"]["type"] == "stale_cache"
    assert body["source_status"]["provider_status"] == "ok"
    assert body["source_status"]["response_type"] == "DataFrame"
    assert body["source_status"]["cache_status"] == "stale_cache"
    assert body["source_context"]["data_status"] == "stale_cache"
    assert body["source_context"]["cache_status"] == "stale_cache"
    assert body["source_context"]["failure_type"] == "stale_cache"
    assert body["source_context"]["source_type"] == "stale_cache"
    assert body["source_context"]["status_reason"] == "当前结果来自旧缓存，需刷新后再执行写入动作"
    for condition in body["parsed_conditions"]:
        assert condition["hit_count"] is None
        assert condition["hit_count_status"] == "stale_cache"
        assert condition["status"] == "degraded_data"
        assert condition["evidence"]["evidence_level"] == "source_status"
    provenance = body["buckets"][0]["items"][0]["candidate_provenance"]
    assert provenance["cache_status"] == "stale_cache"
    assert provenance["provider_status"] == "ok"
    assert provenance["validation_status"] == "unverified"
    assert provenance["matched_conditions"] == []
    _assert_read_only_iwencai_actions(body, has_candidates=True)


def test_iwencai_api_preserves_unsupported_field_without_no_match(client, monkeypatch):
    _install_fake_iwencai_result(
        monkeypatch,
        {
            "data": pd.DataFrame(),
            "provider": "iwencai",
            "provider_status": "ok",
            "failure_type": "unsupported_field",
            "failure_reason": "问财暂不支持字段：ESG评分",
            "response_type": "DataFrame",
            "data_as_of": "2026-06-10T10:00:00+00:00",
            "cache_status": "live_request",
        },
    )

    resp = client.post("/api/llm/iwencai", json={"query": "ESG评分大于80 高股息"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "degraded_data"
    assert body["failure_type"] == "unsupported_field"
    assert body["total"] == 0
    assert body["data"] == []
    assert body["source_status"]["status"] == "degraded_data"
    assert body["source_status"]["type"] == "unsupported_field"
    assert body["source_status"]["reason"] == "问财暂不支持字段：ESG评分"
    assert body["source_context"]["data_status"] == "degraded_data"
    assert body["source_context"]["failure_type"] == "unsupported_field"
    assert body["source_context"]["status_reason"] == "问财暂不支持字段：ESG评分"
    assert body["source_context"]["condition_hit_count"]["高股息"] is None
    condition = body["parsed_conditions"][0]
    assert condition["raw_text"] == "高股息"
    assert condition["hit_count"] is None
    assert condition["hit_count_status"] == "unsupported_field"
    assert condition["status"] == "degraded_data"
    assert condition["missing_reason"] == "问财暂不支持字段：ESG评分"
    assert condition["evidence"]["evidence_level"] == "source_status"
    assert condition["hit_count_status"] != "provider_empty_result"
    assert body["failure_type"] != "no_match"
    _assert_read_only_iwencai_actions(body, has_candidates=False)


def test_iwencai_api_preserves_schema_drift_diagnostics(client, monkeypatch):
    _install_fake_iwencai_result(
        monkeypatch,
        {
            "data": pd.DataFrame(
                [
                    {
                        "股票代码": "600000.SH",
                        "股票简称": "浦发银行",
                        "陌生排名字段": "A1",
                    }
                ]
            ),
            "provider": "iwencai",
            "provider_status": "schema_drift",
            "failure_type": "schema_drift",
            "failure_reason": "问财返回字段结构变化，条件证据需重新适配",
            "response_type": "DataFrame:schema_vNext",
            "schema_signature": "股票代码|股票简称|陌生排名字段",
            "data_as_of": "2026-06-10T10:00:00+00:00",
            "cache_status": "live_request",
        },
    )

    resp = client.post("/api/llm/iwencai", json={"query": "高股息 低估值"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "degraded_data"
    assert body["failure_type"] == "schema_drift"
    assert body["total"] == 1
    assert body["source_status"]["status"] == "degraded_data"
    assert body["source_status"]["provider_status"] == "schema_drift"
    assert body["source_status"]["type"] == "schema_drift"
    assert body["source_status"]["response_type"] == "DataFrame:schema_vNext"
    assert body["source_status"]["schema_signature"] == "股票代码|股票简称|陌生排名字段"
    assert body["source_context"]["response_type"] == "DataFrame:schema_vNext"
    assert body["source_context"]["schema_signature"] == "股票代码|股票简称|陌生排名字段"
    assert body["source_context"]["source_type"] == "schema_drift"
    for condition in body["parsed_conditions"]:
        assert condition["hit_count"] is None
        assert condition["hit_count_status"] == "schema_drift"
        assert condition["status"] == "degraded_data"
        assert condition["evidence"]["evidence_level"] == "source_status"
        assert condition["source_fields"] == []
    provenance = body["buckets"][0]["items"][0]["candidate_provenance"]
    assert provenance["validation_status"] == "unverified"
    assert provenance["matched_conditions"] == []
    assert {item["hit_count_status"] for item in provenance["missing_conditions"]} == {"schema_drift"}
    _assert_read_only_iwencai_actions(body, has_candidates=True)
