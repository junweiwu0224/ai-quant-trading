"""Concrete notification adapters; the domain only depends on their seam."""

from __future__ import annotations

import json
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from engine.events.models import DomainEvent

from .models import DeliveryResult


class InMemoryNotificationAdapter:
    """Deterministic adapter for tests and local dry runs."""

    def __init__(self, *, fail: bool = False, retryable: bool = True) -> None:
        self.fail = fail
        self.retryable = retryable
        self.events: List[DomainEvent] = []

    def send(self, event: DomainEvent) -> DeliveryResult:
        if self.fail:
            return DeliveryResult(
                event_id=event.event_id,
                delivered=False,
                retryable=self.retryable,
                error="in-memory adapter configured to fail",
            )
        self.events.append(event)
        return DeliveryResult(event_id=event.event_id, delivered=True, provider_message_id=event.event_id)


class WebhookNotificationAdapter:
    """Generic JSON webhook adapter with explicit retry classification."""

    def __init__(self, url: str, *, timeout: float = 5.0, transport=None) -> None:
        if not url:
            raise ValueError("webhook url is required")
        self.url = url
        self.timeout = timeout
        self.transport = transport

    def send(self, event: DomainEvent) -> DeliveryResult:
        if self.transport is not None:
            response = self.transport(
                self.url,
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "occurred_at": event.occurred_at,
                    "payload": dict(event.payload),
                },
                {"Content-Type": "application/json", "Idempotency-Key": event.event_id},
                self.timeout,
            )
            status = int(response.get("status_code", response.get("status", 204))) if isinstance(response, dict) else int(response or 204)
            if 200 <= status < 300:
                return DeliveryResult(event_id=event.event_id, delivered=True, status_code=status)
            return DeliveryResult(
                event_id=event.event_id,
                delivered=False,
                retryable=status == 408 or status == 429 or status >= 500,
                error="webhook returned HTTP %d" % status,
                status_code=status,
            )
        payload = json.dumps(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
                "occurred_at": event.occurred_at,
                "payload": dict(event.payload),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self.url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": event.event_id,
                "X-Event-ID": event.event_id,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = int(response.getcode())
            if 200 <= status < 300:
                return DeliveryResult(event_id=event.event_id, delivered=True)
            return DeliveryResult(
                event_id=event.event_id,
                delivered=False,
                retryable=status == 429 or status >= 500,
                error="webhook returned HTTP %d" % status,
            )
        except HTTPError as exc:
            return DeliveryResult(
                event_id=event.event_id,
                delivered=False,
                retryable=exc.code == 429 or exc.code >= 500,
                error="webhook returned HTTP %d" % exc.code,
            )
        except URLError as exc:
            return DeliveryResult(event_id=event.event_id, delivered=False, retryable=True, error=str(exc.reason))
        except OSError as exc:
            return DeliveryResult(event_id=event.event_id, delivered=False, retryable=True, error=str(exc))


class AlertWebhookNotificationAdapter:
    """Route alert events to the rule-specific webhook in their payload.

    Alerts without a configured webhook are explicitly blocked.  A durable
    event is not proof that an external consumer received anything.
    """

    def send(self, event: DomainEvent) -> DeliveryResult:
        url = str(dict(event.payload).get("webhook_url") or "").strip()
        if not url:
            return DeliveryResult(
                event_id=event.event_id,
                delivered=False,
                retryable=False,
                error="alert webhook is not configured",
                details={"blocked": "no_webhook_configured"},
            )
        result = WebhookNotificationAdapter(url).send(event)
        if result.event_id == event.event_id:
            return result
        return DeliveryResult(
            event_id=event.event_id,
            delivered=result.delivered,
            retryable=result.retryable,
            error=result.error,
            provider_message_id=result.provider_message_id,
            status_code=result.status_code,
            response_body=result.response_body,
            retry_after=result.retry_after,
            details=result.details,
        )


class DailyBriefNotificationAdapter:
    """Route daily brief events to an explicit configured webhook.

    No URL is a permanent configuration block, never a successful delivery.
    """

    def __init__(self, url: str = "", *, timeout: float = 5.0, transport=None) -> None:
        self.url = str(url or "").strip()
        self.timeout = timeout
        self.transport = transport

    def send(self, event: DomainEvent) -> DeliveryResult:
        if not self.url:
            return DeliveryResult(
                event_id=event.event_id,
                delivered=False,
                retryable=False,
                error="daily brief webhook is not configured",
                details={"blocked": "daily_brief_webhook_not_configured"},
            )
        return WebhookNotificationAdapter(self.url, timeout=self.timeout, transport=self.transport).send(event)
