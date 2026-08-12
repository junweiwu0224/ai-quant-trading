"""Reserved seam for a future WebSocket notification adapter.

The existing ``engine.alert_engine`` owns its current WebSocket behavior and
is intentionally not imported or modified here.  This placeholder makes the
future adapter boundary explicit without opening a socket or changing alert
delivery semantics today.
"""

from __future__ import annotations

from engine.events import DomainEvent

from .models import DeliveryResult


class FutureWebSocketAdapter:
    """Non-operational placeholder; a future adapter must be injected."""

    def deliver(self, event: DomainEvent) -> DeliveryResult:
        raise NotImplementedError(
            "WebSocket delivery is reserved for a future adapter and is not wired"
        )

    send = deliver


WebSocketAdapter = FutureWebSocketAdapter

__all__ = ["FutureWebSocketAdapter", "WebSocketAdapter"]
