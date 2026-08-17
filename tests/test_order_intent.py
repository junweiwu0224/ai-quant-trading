from agentic.models import TradingSignal
from agentic.order_intent import InMemoryPaperExecutionAdapter, OrderIntentService
from agentic.promotion import PromotionContext, PromotionPolicy


def test_order_intent_is_paper_only_and_requires_confirmation():
    signal = TradingSignal(
        id="sig-1",
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
    service = OrderIntentService(max_volume=100)
    intent = service.create(signal, decision, volume=100)
    assert intent.paper_only
    assert intent.status == "pending_confirmation"
    confirmed = service.confirm(intent, confirmed_by="user-1")
    adapter = InMemoryPaperExecutionAdapter()
    submitted = service.submit_to_paper(confirmed, adapter)
    assert submitted.status == "paper_submitted"
    assert adapter.submitted == [submitted]
