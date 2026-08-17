"""Turn claimed outbox messages into adapter attempts."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from engine.events.outbox import SQLiteOutbox

from .models import DeliveryResult, NotificationAdapter


class NotificationDispatcher:
    """Own the claim and acknowledgement lifecycle for one consumer."""

    def __init__(
        self,
        outbox: SQLiteOutbox,
        adapter: NotificationAdapter,
        *,
        consumer: str = "notifications",
        event_types: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> None:
        self.outbox = outbox
        self.adapter = adapter
        self.consumer = consumer
        self.event_types = tuple(dict.fromkeys(str(item) for item in (event_types or ()) if str(item)))

    def dispatch(self, *, limit: int = 20, now: Optional[datetime] = None) -> List[DeliveryResult]:
        results: List[DeliveryResult] = []
        for message in self.outbox.claim(
            consumer=self.consumer,
            limit=limit,
            now=now,
            event_types=self.event_types,
        ):
            try:
                result = self.adapter.send(message.event)
            except Exception as exc:
                result = DeliveryResult(
                    event_id=message.event.event_id,
                    delivered=False,
                    retryable=True,
                    error=str(exc),
                )
            if result.delivered:
                self.outbox.mark_delivered(
                    message.event.event_id,
                    consumer=self.consumer,
                    claim_token=message.claim_token or "",
                )
            else:
                self.outbox.mark_failed(
                    message.event.event_id,
                    consumer=self.consumer,
                    claim_token=message.claim_token or "",
                    error=result.error or "notification adapter failed",
                    retryable=result.retryable,
                    retry_after=result.retry_after,
                    now=now,
                )
            results.append(result)
        return results
