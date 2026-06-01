from dataclasses import dataclass


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

    def create_intent(self, signal, cash):
        if signal.status != "paper_pending":
            raise ValueError("Only paper_pending signals can create paper intents")
        if signal.direction not in {"buy", "sell"}:
            raise ValueError("Paper intents only support buy/sell directions")

        return PaperIntent(
            signal_id=signal.signal_id,
            agent_id=signal.agent_id,
            code=signal.code,
            direction=signal.direction,
            amount=cash * signal.suggested_position,
            reason="; ".join(signal.entry_reasons),
        )
