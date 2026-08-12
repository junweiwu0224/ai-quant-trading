from pathlib import Path


def test_intelligence_market_surfaces_evidence_snapshot():
    source = (Path(__file__).resolve().parents[1] / "dashboard" / "static" / "intelligence-market.js").read_text()
    assert "evidence_snapshot_id" in source


def test_stock_news_route_uses_evidence_snapshot_collector():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "dashboard" / "routers" / "stock_detail.py").read_text()
    assert "collect_stock_news_evidence" in source
    assert 'DB_DIR / "evidence.db"' in source
