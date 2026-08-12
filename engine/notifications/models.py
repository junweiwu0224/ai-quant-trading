"""Notification delivery records and the transport Adapter Interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Protocol

from engine.events.models import DomainEvent


class DeliveryStatus(str, Enum):
    DELIVERED = "delivered"
    RETRYABLE = "retryable"
    PERMANENT_FAILURE = "permanent_failure"


class FailureKind(str, Enum):
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


FailureClass = FailureKind


class DeliveryFailure(RuntimeError):
    """Base exception for an Adapter that classifies transport failure."""


class RetryableDeliveryError(DeliveryFailure):
    pass


class PermanentDeliveryError(DeliveryFailure):
    pass


@dataclass(frozen=True)
class DeliveryResult:
    event_id: Optional[str] = None
    delivered: bool = False
    retryable: bool = False
    error: Optional[str] = None
    provider_message_id: Optional[str] = None
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    retry_after: Optional[float] = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> DeliveryStatus:
        if self.delivered:
            return DeliveryStatus.DELIVERED
        if self.retryable:
            return DeliveryStatus.RETRYABLE
        return DeliveryStatus.PERMANENT_FAILURE

    @classmethod
    def success_result(
        cls,
        *,
        event_id: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ) -> "DeliveryResult":
        return cls(
            event_id=event_id,
            delivered=True,
            status_code=status_code,
            response_body=response_body,
        )

    @classmethod
    def retryable_failure(
        cls,
        error: str,
        *,
        event_id: Optional[str] = None,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
        response_body: Optional[str] = None,
    ) -> "DeliveryResult":
        return cls(
            event_id=event_id,
            delivered=False,
            retryable=True,
            error=error,
            status_code=status_code,
            retry_after=retry_after,
            response_body=response_body,
        )

    @classmethod
    def permanent_failure(
        cls,
        error: str,
        *,
        event_id: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> "DeliveryResult":
        return cls(
            event_id=event_id,
            delivered=False,
            retryable=False,
            error=error,
            status_code=status_code,
            response_body=response_body,
            details=dict(details or {}),
        )


class NotificationAdapter(Protocol):
    def send(self, event: DomainEvent) -> DeliveryResult: ...
