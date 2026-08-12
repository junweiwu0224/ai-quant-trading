"""Notification adapters behind the durable outbox seam."""

from .adapters import AlertWebhookNotificationAdapter, InMemoryNotificationAdapter, WebhookNotificationAdapter
from .dispatcher import NotificationDispatcher
from .models import DeliveryResult, NotificationAdapter

__all__ = [
    "DeliveryResult",
    "NotificationAdapter",
    "InMemoryNotificationAdapter",
    "WebhookNotificationAdapter",
    "AlertWebhookNotificationAdapter",
    "NotificationDispatcher",
]
