from agentic.models import TradingSignal
from agentic.promotion import PromotionContext, PromotionPolicy
from agentic.signals import SignalService


class FakeSignalRepository:
    def __init__(self, db_path):
        self.db_path = db_path
        self.signals = {}

    def save_signal(self, signal: TradingSignal) -> None:
        self.signals[signal.id] = signal

    def get_signal(self, signal_id: str) -> TradingSignal:
        return self.signals[signal_id]

    def list_signals(self, limit: int = 100) -> list[TradingSignal]:
        return list(self.signals.values())[:limit]


def test_signal_service_writes_projection_and_ledger(tmp_path):
    service = SignalService(FakeSignalRepository(tmp_path / "agentic.db"))
    signal = service.publish(
        agent_id="agent-1",
        source="fixture",
        code="600000",
        direction="buy",
        confidence=0.8,
        time_horizon="swing",
        entry_reasons=["fixture evidence"],
        risk_notes=["fixture risk"],
        suggested_position=0.1,
    )
    assert [event.to_status for event in service.ledger.timeline(signal.id)] == ["new"]
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
    updated = service.mark_paper_pending(signal.id, confirmed_by="user-1", decision=decision)
    assert updated.status == "paper_pending"
    assert [event.to_status for event in service.ledger.timeline(signal.id)] == ["new", "paper_pending"]
