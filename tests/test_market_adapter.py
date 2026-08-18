"""Tests for MarketAdapter contract and data health endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    from dashboard.app import app
    return TestClient(app)


class TestMarketCapabilityEndpoint:
    """Test /api/markets endpoint."""

    def test_get_markets_returns_six_markets(self, client):
        """Should return all 6 markets."""
        response = client.get("/api/market/markets")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["total"] == 6
        assert len(data["markets"]) == 6

        market_codes = {m["code"] for m in data["markets"]}
        assert market_codes == {"CN", "HK", "US", "JP", "KR", "TW"}

    def test_cn_market_is_active(self, client):
        """CN market should be active with capabilities."""
        response = client.get("/api/market/markets")
        data = response.json()

        cn_market = next(m for m in data["markets"] if m["code"] == "CN")
        assert cn_market["status"] == "active"
        assert cn_market["name_zh"] == "A股"
        assert cn_market["name_en"] == "China A-shares"
        assert "日线" in cn_market["capabilities"]
        assert cn_market["provider"] == "akshare"
        assert cn_market["timezone"] == "Asia/Shanghai"
        assert cn_market["currency"] == "CNY"

    def test_other_markets_are_unavailable(self, client):
        """HK/US/JP/KR/TW markets should be unavailable."""
        response = client.get("/api/market/markets")
        data = response.json()

        for code in ["HK", "US", "JP", "KR", "TW"]:
            market = next(m for m in data["markets"] if m["code"] == code)
            assert market["status"] == "unavailable"
            assert market["provider"] is None
            assert market["reason"] == "数据源未接入"
            assert len(market["capabilities"]) == 0

    def test_markets_have_trading_hours(self, client):
        """All markets should have trading hours."""
        response = client.get("/api/market/markets")
        data = response.json()

        for market in data["markets"]:
            assert "trading_hours" in market
            assert "open" in market["trading_hours"]
            assert "close" in market["trading_hours"]
            assert "timezone" in market
            assert "currency" in market

    def test_markets_response_is_cached(self, client):
        """Markets endpoint should return cached response."""
        response1 = client.get("/api/market/markets")
        response2 = client.get("/api/market/markets")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["generated_at"] == response2.json()["generated_at"]

    def test_canonical_capabilities_expose_manual_research_provider(self, client):
        response = client.get("/api/market/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "data.markets.MARKET_ADAPTERS"
        assert {item["code"] for item in data["markets"]} == {"CN", "HK", "US", "JP", "KR", "TW"}
        for code in ["HK", "US", "JP", "KR", "TW"]:
            market = next(item for item in data["markets"] if item["code"] == code)
            assert market["manual_research"] is True
            assert market["data_state"] == "configured"
            assert market["provider"] == "Yahoo Finance"
            assert market["scheduled_daily_report"] is False
            assert market["intraday_auto_push"] is False

    def test_legacy_markets_share_canonical_provider_metadata(self, client):
        legacy = client.get("/api/market/markets").json()
        canonical = client.get("/api/market/capabilities").json()
        legacy_by_code = {item["code"]: item for item in legacy["markets"]}
        canonical_by_code = {item["code"]: item for item in canonical["markets"]}
        for code in ("CN", "HK", "US", "JP", "KR", "TW"):
            assert legacy_by_code[code]["provider_details"] == canonical_by_code[code]["provider_details"]
            assert legacy_by_code[code]["data_state"] == canonical_by_code[code]["data_state"]

    @pytest.mark.parametrize(
        ("path", "collection"),
        [
            ("/api/market/breadth?market=HK", None),
            ("/api/market/radar?market=US&fast=true", "items"),
            ("/api/market/sectors?market=JP&fast=true", "sectors"),
            ("/api/market/heatmap?market=KR&fast=true", "sectors"),
            ("/api/market/hotspot?market=TW", "hotspots"),
            ("/api/market/news?market=HK", "news"),
        ],
    )
    def test_non_cn_market_intelligence_never_reuses_cn_feed(self, client, path, collection):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["market"] in {"HK", "US", "JP", "KR", "TW"}
        assert payload["source"] in {"market_capability", "yahoo_finance", "yahoo_finance_search", "yahoo_finance_chart", "yahoo_finance_rss"}
        assert payload["data_state"] in {"not_integrated", "manual_research", "unavailable"}
        assert payload["manual_research_only"] is True
        assert payload["authoritative"] is False
        if collection:
            assert isinstance(payload[collection], list)
            for item in payload[collection]:
                assert item.get("proxy") is True or payload.get("proxy_type") in {"sector_etf", "ticker_news", "universe_search"}

    def test_unknown_market_is_rejected_instead_of_being_reported_unavailable(self, client):
        response = client.get("/api/market/breadth?market=ZZ")

        assert response.status_code == 400
        assert response.json()["detail"] == "无效市场: ZZ"


class TestDataHubHealthEndpoint:
    """Test enhanced /api/datahub/health endpoint."""

    def test_health_includes_overall_status(self, client):
        """Health endpoint should include overall status."""
        response = client.get("/api/datahub/health")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unavailable"]

    def test_health_includes_markets_section(self, client):
        """Health endpoint should include markets health."""
        response = client.get("/api/datahub/health")
        data = response.json()

        assert "markets" in data
        assert "CN" in data["markets"]

        cn_health = data["markets"]["CN"]
        assert "status" in cn_health
        assert "provider" in cn_health
        assert "coverage" in cn_health
        assert "capabilities" in cn_health

    def test_cn_market_health_has_details(self, client):
        """CN market health should include detailed metrics."""
        response = client.get("/api/datahub/health")
        data = response.json()

        cn_health = data["markets"]["CN"]
        assert cn_health["status"] in ["healthy", "degraded", "unavailable"]
        assert cn_health["provider"] == "akshare"
        assert isinstance(cn_health["coverage"], (int, float))
        assert isinstance(cn_health["capabilities"], list)
        assert "stock_count" in cn_health

    def test_other_markets_show_unavailable(self, client):
        """Other markets should show unavailable in health."""
        response = client.get("/api/datahub/health")
        data = response.json()

        for code in ["HK", "US", "JP", "KR", "TW"]:
            market_health = data["markets"][code]
            assert market_health["status"] == "unavailable"
            assert "reason" in market_health

    def test_configured_manual_markets_are_not_reported_as_zero_coverage(self, client):
        data = client.get("/api/datahub/health?fast=true").json()
        for code in ("HK", "US", "JP", "KR", "TW"):
            health = data["markets"][code]
            assert health["research_status"] == "manual_research"
            assert health["data_state"] == "configured"
            assert health["coverage_pct"] is None
            assert health["stale"] is False

    def test_cn_runtime_health_requires_actual_daily_coverage(self):
        from dashboard.routers.datahub import _cn_market_runtime_state

        status, coverage = _cn_market_runtime_state(2, {"stock_count": 2, "daily_covered": 0})
        assert status == "degraded"
        assert coverage == 0.0

        status, coverage = _cn_market_runtime_state(2, {"stock_count": 2, "daily_covered": 1})
        assert status == "healthy"
        assert coverage == 0.5

    def test_health_fast_mode(self, client):
        """Health endpoint should support fast mode."""
        response = client.get("/api/datahub/health?fast=true")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "markets" in data
        assert "signal" in data

    def test_health_backward_compatibility(self, client):
        """Health endpoint should maintain backward compatibility."""
        response = client.get("/api/datahub/health")
        data = response.json()

        # Legacy fields should still exist
        assert "stock_count" in data
        assert "stock_daily" in data
        assert "source_health" in data
        assert "quality_summary" in data
        assert "quote" in data
        assert "valuation" in data
        assert "signal" in data
        assert "qlib" in data
        assert "providers" in data


class TestMarketCapabilityContract:
    """Test MarketCapability data structure contract."""

    def test_market_capability_structure(self, client):
        """Market capability should follow the contract."""
        response = client.get("/api/market/markets")
        data = response.json()

        for market in data["markets"]:
            # Required fields
            assert "code" in market
            assert "name_zh" in market
            assert "name_en" in market
            assert "status" in market
            assert "capabilities" in market
            assert "trading_hours" in market
            assert "timezone" in market
            assert "currency" in market

            # Validate types
            assert isinstance(market["code"], str)
            assert isinstance(market["name_zh"], str)
            assert isinstance(market["name_en"], str)
            assert market["status"] in ["active", "limited", "unavailable"]
            assert isinstance(market["capabilities"], list)
            assert isinstance(market["trading_hours"], dict)
            assert isinstance(market["timezone"], str)
            assert isinstance(market["currency"], str)

    def test_trading_hours_structure(self, client):
        """Trading hours should follow the contract."""
        response = client.get("/api/market/markets")
        data = response.json()

        for market in data["markets"]:
            hours = market["trading_hours"]
            assert "open" in hours
            assert "close" in hours
            # lunch_start and lunch_end are optional

    def test_capability_values(self, client):
        """Capabilities should use standardized values."""
        response = client.get("/api/market/markets")
        data = response.json()

        valid_capabilities = {"日线", "分时", "盘口", "实时", "历史"}
        for market in data["markets"]:
            for cap in market["capabilities"]:
                assert cap in valid_capabilities


class TestDataHealthContract:
    """Test data health response contract."""

    def test_health_market_section_structure(self, client):
        """Health markets section should follow contract."""
        response = client.get("/api/datahub/health")
        data = response.json()

        # Check overall structure
        assert "status" in data
        assert "markets" in data
        assert isinstance(data["markets"], dict)

        # Check CN market detail structure
        cn = data["markets"]["CN"]
        assert "status" in cn
        assert "provider" in cn
        assert "last_update" in cn
        assert "coverage" in cn
        assert "capabilities" in cn
        assert "stock_count" in cn

    def test_health_status_values(self, client):
        """Health status should use valid values."""
        response = client.get("/api/datahub/health")
        data = response.json()

        assert data["status"] in ["healthy", "degraded", "unavailable"]
        for market_health in data["markets"].values():
            assert market_health["status"] in ["healthy", "degraded", "unavailable"]


class TestMarketAdapterIntegration:
    """Integration tests for market adapter system."""

    def test_markets_and_health_consistency(self, client):
        """Markets and health endpoints should be consistent."""
        markets_resp = client.get("/api/market/markets")
        health_resp = client.get("/api/datahub/health")

        markets_data = markets_resp.json()
        health_data = health_resp.json()

        # Check that all markets in /api/markets appear in health
        for market in markets_data["markets"]:
            code = market["code"]
            assert code in health_data["markets"]

    def test_cn_market_capabilities_match_health(self, client):
        """CN market capabilities should match between endpoints."""
        markets_resp = client.get("/api/market/markets")
        health_resp = client.get("/api/datahub/health")

        markets_data = markets_resp.json()
        health_data = health_resp.json()

        cn_market = next(m for m in markets_data["markets"] if m["code"] == "CN")
        cn_health = health_data["markets"]["CN"]

        # Capabilities should match
        assert set(cn_market["capabilities"]) == set(cn_health["capabilities"])

    def test_unavailable_markets_consistent(self, client):
        """Unavailable markets should be consistent across endpoints."""
        markets_resp = client.get("/api/market/markets")
        health_resp = client.get("/api/datahub/health")

        markets_data = markets_resp.json()
        health_data = health_resp.json()

        for code in ["HK", "US", "JP", "KR", "TW"]:
            market = next(m for m in markets_data["markets"] if m["code"] == code)
            health = health_data["markets"][code]

            assert market["status"] == "unavailable"
            assert health["status"] == "unavailable"
