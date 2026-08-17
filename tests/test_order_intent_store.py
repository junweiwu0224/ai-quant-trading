import sqlite3

from agentic.models import TradingSignal
from agentic.order_intent import OrderIntentService
from agentic.order_intent_store import SQLiteOrderIntentStore
from agentic.promotion import PromotionContext, PromotionPolicy


def test_order_intent_state_is_durable_and_auditable():
    store = SQLiteOrderIntentStore(sqlite3.connect(":memory:"))
    signal = TradingSignal(
        id="sig-store",
        agent_id="agent-1",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.9,
        time_horizon="swing",
        entry_reasons=["evidence"],
        risk_notes=["risk"],
        suggested_position=0.1,
        stop_loss=0.05,
        take_profit=0.1,
        status="new",
        created_at="2026-08-12T00:00:00Z",
    )
    decision = PromotionPolicy().evaluate(
        PromotionContext(
            evidence_count=1,
            provenance_complete=True,
            backtest_passed=True,
            risk_approved=True,
            signal_validation_passed=True,
        ),
        target="paper_pending",
    )
    service = OrderIntentService(max_volume=100, store=store)
    intent = service.create(signal, decision, volume=100)
    service.confirm(intent, confirmed_by="user-1")
    persisted = store.get(intent.id)
    assert persisted is not None
    assert persisted.status == "confirmed"
    assert persisted.paper_only
