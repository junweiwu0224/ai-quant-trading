"""Generic webhook adapter with an injectable, non-networking transport seam."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import inspect
import json
from typing import Any, Protocol, runtime_checkable

from engine.events import DomainEvent

from .models import (
    DeliveryResult,
    PermanentDeliveryError,
    RetryableDeliveryError,
)


@runtime_checkable
class NotificationAdapter(Protocol):
    """Canonical notification Adapter interface."""

    def send(self, event: DomainEvent) -> DeliveryResult: ...


@runtime_checkable
class WebhookTransport(Protocol):
    """Test-injectable transport contract.

    Implementations may expose ``post`` or be callable.  The adapter accepts
    common two/four argument test doubles as well as an HTTP-client-like
    ``post(url, json=..., headers=..., timeout=...)`` method.
    """

    def __call__(
        self,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: float,
    ) -> Any: ...


class GenericWebhookAdapter:
    """Turn a :class:`DomainEvent` into a JSON-ready webhook delivery.

    No default HTTP client is used.  With no injected transport the adapter
    returns a permanent configuration failure, so merely constructing or
    calling it cannot send data to an external service.
    """

    def __init__(
        self,
        url: str,
        transport: WebhookTransport | Callable[..., Any] | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("webhook url must be a non-empty string")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.url = url.strip()
        self.transport = transport
        self.headers = dict(headers or {})
        self.timeout = float(timeout)

    @staticmethod
    def payload_for(event: DomainEvent) -> dict[str, Any]:
        if not isinstance(event, DomainEvent):
            raise TypeError("webhook adapter accepts DomainEvent instances")
        return json.loads(event.to_json())

    def send(self, event: DomainEvent) -> DeliveryResult:
        payload = self.payload_for(event)
        if self.transport is None:
            return DeliveryResult.permanent_failure(
                "no webhook transport configured",
                event_id=event.event_id,
                details={"event_id": event.event_id},
            )

        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": event.event_id,
            "X-Event-ID": event.event_id,
        }
        request_headers.update(self.headers)

        try:
            response = _invoke_transport(
                self.transport,
                self.url,
                payload,
                request_headers,
                self.timeout,
            )
        except PermanentDeliveryError as exc:
            return DeliveryResult.permanent_failure(str(exc))
        except RetryableDeliveryError as exc:
            return DeliveryResult.retryable_failure(str(exc))
        except (TimeoutError, OSError, ConnectionError) as exc:
            return DeliveryResult.retryable_failure(str(exc) or exc.__class__.__name__)
        except Exception as exc:  # Unknown transport failures are safer to retry.
            return DeliveryResult.retryable_failure(
                str(exc) or exc.__class__.__name__,
            )

        if isinstance(response, DeliveryResult):
            return response
        status_code, response_body, response_headers = _response_parts(response)
        if status_code is None:
            # A no-return test double represents a completed send.  Real
            # transports should return a response or raise an exception.
            status_code = 204
        return _result_for_status(
            status_code,
            event_id=event.event_id,
            response_body=response_body,
            response_headers=response_headers,
        )

    # ``deliver`` remains a compatibility alias for older callers; the
    # public seam used by NotificationDispatcher is ``send``.
    deliver = send
    publish = deliver

    def __call__(self, event: DomainEvent) -> DeliveryResult:
        return self.deliver(event)


WebhookAdapter = GenericWebhookAdapter


def _invoke_transport(
    transport: WebhookTransport | Callable[..., Any],
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    timeout: float,
) -> Any:
    target = getattr(transport, "post", None) or transport
    candidates = [
        ((url,), {"json": payload, "headers": headers, "timeout": timeout}),
        ((url, payload, headers, timeout), {}),
        ((url, payload, headers), {}),
        ((url, payload), {}),
    ]
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return target(url, payload, headers, timeout)

    for args, kwargs in candidates:
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            continue
        return target(*args, **kwargs)
    raise TypeError(
        "webhook transport must accept (url, payload[, headers[, timeout]]) "
        "or an HTTP-client-like post method"
    )


def _response_parts(
    response: Any,
) -> tuple[int | None, str | None, Mapping[str, Any]]:
    if response is None:
        return None, None, {}
    if isinstance(response, bool):
        return (204 if response else 503), None, {}
    if isinstance(response, int):
        return response, None, {}
    if isinstance(response, tuple):
        if not response:
            return None, None, {}
        status = response[0]
        body = response[1] if len(response) > 1 else None
        return int(status), None if body is None else str(body), {}
    if isinstance(response, Mapping):
        status = response.get("status_code", response.get("status"))
        if status is None:
            return (
                None,
                _body_text(response.get("body", response.get("text"))),
                response.get("headers", {}),
            )
        return (
            int(status),
            _body_text(response.get("body", response.get("text"))),
            response.get("headers", {}),
        )

    status = getattr(response, "status_code", getattr(response, "status", None))
    body = getattr(response, "text", getattr(response, "body", None))
    headers = getattr(response, "headers", {}) or {}
    return (int(status) if status is not None else None, _body_text(body), headers)


def _body_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _result_for_status(
    status_code: int,
    *,
    event_id: str | None = None,
    response_body: str | None,
    response_headers: Mapping[str, Any],
) -> DeliveryResult:
    if 200 <= status_code < 300:
        return DeliveryResult.success_result(
            event_id=event_id,
            status_code=status_code,
            response_body=response_body,
        )

    retryable = status_code in {408, 425, 429} or status_code >= 500
    message = f"webhook returned HTTP {status_code}"
    if retryable:
        retry_after = _retry_after_header(response_headers)
        return DeliveryResult.retryable_failure(
            message,
            event_id=event_id,
            status_code=status_code,
            retry_after=retry_after,
            response_body=response_body,
        )
    return DeliveryResult.permanent_failure(
        message,
        event_id=event_id,
        status_code=status_code,
        response_body=response_body,
    )


def _retry_after_header(headers: Mapping[str, Any]) -> float | None:
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


__all__ = [
    "GenericWebhookAdapter",
    "NotificationAdapter",
    "WebhookAdapter",
    "WebhookTransport",
]
