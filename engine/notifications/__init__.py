"""Notification adapters behind the durable outbox seam."""

from .adapters import AlertWebhookNotificationAdapter, DailyBriefNotificationAdapter, InMemoryNotificationAdapter, WebhookNotificationAdapter
from .channels import (
    FeishuRobotNotificationAdapter,
    PushPlusNotificationAdapter,
    QQOfficialBotNotificationAdapter,
    WeComRobotNotificationAdapter,
)
from .dispatcher import NotificationDispatcher
from .models import AmbiguousDeliveryError, DeliveryResult, NotificationAdapter

__all__ = [
    "DeliveryResult",
    "AmbiguousDeliveryError",
    "NotificationAdapter",
    "InMemoryNotificationAdapter",
    "WebhookNotificationAdapter",
    "AlertWebhookNotificationAdapter",
    "DailyBriefNotificationAdapter",
    "WeComRobotNotificationAdapter",
    "PushPlusNotificationAdapter",
    "FeishuRobotNotificationAdapter",
    "QQOfficialBotNotificationAdapter",
    "NotificationDispatcher",
]
