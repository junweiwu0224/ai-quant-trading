import asyncio

from alpha import hotspot_attribution


def test_hotspot_attribution_reports_partial_source_failures(monkeypatch):
    async def empty_concepts(top_n=20):
        return []

    async def industries(top_n=20):
        return [{
            "name": "工业金属",
            "change_pct": 1.76,
            "leader": "铜陵有色",
            "up_count": 24,
            "down_count": 5,
        }]

    async def flow(top_n=20):
        return [{
            "name": "有色金属",
            "change_pct": 1.2,
            "main_net_inflow": 12.35,
            "main_net_inflow_pct": 4.8,
        }]

    monkeypatch.setattr(hotspot_attribution, "get_hot_concepts", empty_concepts)
    monkeypatch.setattr(hotspot_attribution, "get_hot_industries", industries)
    monkeypatch.setattr(hotspot_attribution, "get_sector_fund_flow", flow)

    data = asyncio.run(hotspot_attribution.get_hotspot_attribution())

    assert data["summary"] == "暂无热点数据"
    assert "concept" in data["partial_errors"]
    assert data["source_status"]["concept"]["ok"] is False
    assert data["source_status"]["industry"]["ok"] is True
    assert data["source_status"]["fund_flow"]["ok"] is True


def test_board_ranking_uses_leader_name_and_preserves_code(monkeypatch):
    def fake_fetch_json(url, timeout=10):
        return {
            "data": {
                "diff": [{
                    "f12": "BK1101",
                    "f14": "先进封装",
                    "f3": 2.36,
                    "f104": 20,
                    "f105": 16,
                    "f128": "三佳科技",
                    "f140": "600520",
                    "f136": 10.01,
                    "f20": 2603874784000,
                }]
            }
        }

    monkeypatch.setattr(hotspot_attribution, "fetch_json", fake_fetch_json)

    rows = hotspot_attribution._fetch_board_ranking("concept", 1)

    assert rows[0]["leader"] == "三佳科技"
    assert rows[0]["leader_code"] == "600520"


def test_sector_fund_flow_prefers_delay_host_when_primary_is_unstable(monkeypatch):
    calls = []

    def fake_fetch_json(url, timeout=10):
        calls.append(url)
        if "push2delay.eastmoney.com" not in url:
            raise AssertionError("delay host should be tried before unstable primary host")
        return {
            "data": {
                "diff": [{
                    "f12": "BK1204",
                    "f14": "国防军工",
                    "f3": 1.07,
                    "f62": 2108379136.0,
                    "f184": 2.22,
                }]
            }
        }

    monkeypatch.setattr(hotspot_attribution, "fetch_json", fake_fetch_json)

    rows = hotspot_attribution._fetch_sector_fund_flow(10)

    assert len(calls) == 1
    assert rows == [{
        "code": "BK1204",
        "name": "国防军工",
        "change_pct": 1.07,
        "main_net_inflow": 21.08,
        "main_net_inflow_pct": 2.22,
    }]
