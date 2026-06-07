from agentic.models import TradingSignal
from agentic.paper_bridge import PaperBridge, PaperIntent


class FakeOrderManager:
    def __init__(self):
        self.orders = []

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"id": "order_1", **kwargs}


def test_paper_bridge_creates_order_intent_not_direct_order_by_default():
    bridge = PaperBridge(order_manager=FakeOrderManager())
    signal = TradingSignal(
        "sig_1",
        "signal_agent",
        "signal",
        "605066",
        "buy",
        0.75,
        "3-10d",
        ["AI signal Top"],
        ["stop loss required"],
        0.1,
        0.05,
        0.12,
        "paper_pending",
        "2026-06-01T15:00:00+08:00",
    )

    intent = bridge.create_intent(signal, cash=50000)

    assert isinstance(intent, PaperIntent)
    assert intent.code == "605066"
    assert intent.amount == 5000
    assert bridge.order_manager.orders == []
