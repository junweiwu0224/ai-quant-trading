from __future__ import annotations

from dataclasses import dataclass

from agentic.models import TradingSignal


@dataclass(frozen=True)
class PaperIntent:
    signal_id: str
    agent_id: str
    code: str
    direction: str
    amount: float
    reason: str
    requires_confirmation: bool = True


class PaperBridge:
    def __init__(self, order_manager=None):
        self.order_manager = order_manager

    def create_intent(self, signal: TradingSignal, cash: float) -> PaperIntent:
        if signal.status != "paper_pending":
            raise ValueError("signal must be paper_pending before creating paper intent")
        if signal.direction not in {"buy", "sell"}:
            raise ValueError("only buy/sell signals can create paper intents")

        return PaperIntent(
            signal_id=signal.id,
            agent_id=signal.agent_id,
            code=signal.code,
            direction=signal.direction,
            amount=round(float(cash) * float(signal.suggested_position), 2),
            reason="; ".join(signal.entry_reasons[:3]),
            requires_confirmation=True,
        )
