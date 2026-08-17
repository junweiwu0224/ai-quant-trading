import sqlite3

from agentic.daily_workflow import DailyWorkflowRunner, SignalCandidate
from agentic.promotion import PromotionContext, PromotionPolicy
from agentic.signal_ledger import SignalLedger
from data.evidence.models import EvidenceItem, EvidenceSource
from data.evidence.store import InMemoryEvidenceStore
from engine.events.outbox import SQLiteOutbox


def test_daily_workflow_links_evidence_to_promotion_and_brief_event():
    evidence = InMemoryEvidenceStore()
    ledger = SignalLedger(sqlite3.connect(":memory:"))
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    runner = DailyWorkflowRunner(evidence, ledger, PromotionPolicy(), outbox)
    brief = runner.run(
        watchlist=["600000.SH"],
        source=EvidenceSource(id="fixture", name="Fixture", kind="test", trust_tier="test"),
        evidence_items=[
            EvidenceItem(
                id="e-1",
                source_id="fixture",
                title="News",
                content="A fact",
                observed_at="2026-08-12T08:00:00Z",
                symbol="600000.SH",
            )
        ],
        candidates=[
            SignalCandidate(
                signal_id="sig-1",
                symbol="600000.SH",
                from_status=None,
                target="paper_pending",
                context=PromotionContext(
                    provenance_complete=True,
                    backtest_passed=True,
                    risk_approved=True,
                    signal_validation_passed=True,
                ),
            )
        ],
    )
    assert brief.evidence_count == 1
    assert brief.promotions[0].decision.approved
    assert ledger.timeline("sig-1")[0].to_status == "paper_pending"
    assert outbox.get(brief.event_id).event.event_type == "daily.brief.ready"
