from pathlib import Path


def test_audit_router_is_registered_and_market_news_exposes_evidence_reference():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "dashboard" / "app.py").read_text()
    market_source = (root / "dashboard" / "routers" / "market.py").read_text()
    audit_source = (root / "dashboard" / "routers" / "audit.py").read_text()
    assert "agentic, account, alerts, alpha, audit," in app_source
    assert 'app.include_router(audit.router, prefix="/api", tags=["审计"])' in app_source
    assert 'router = APIRouter(prefix="/audit", tags=["audit"])' in audit_source
    assert '@router.get("/signals/{signal_id}")' in audit_source
    assert '@router.get("/evidence/{snapshot_id}")' in audit_source
    assert "collect_market_news_evidence" in market_source
    assert "evidence_store = SQLiteEvidenceStore" in market_source
