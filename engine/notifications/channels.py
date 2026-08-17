"""Provider-specific notification adapters behind the durable outbox seam.

These adapters intentionally do not create an HTTP client.  A worker supplies a
``transport`` when external delivery has been explicitly configured; without
one, ``send`` returns a permanent configuration failure and performs no I/O.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping, Optional

from engine.events.models import DomainEvent

from .models import (
    AmbiguousDeliveryError,
    DeliveryResult,
    PermanentDeliveryError,
    RetryableDeliveryError,
)


NotificationTransport = Callable[[str, Mapping[str, Any], Mapping[str, str], float], Any]

_SENSITIVE_KEY_RE = re.compile(
    r"(?:token|secret|password|credential|authorization|api[_-]?key|access[_-]?key|webhook[_-]?url)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?P<name>token|secret|password|credential|authorization|api[_-]?key|access[_-]?key)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;&]+)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_RE = re.compile(
    r"(?P<name>[?&](?:token|secret|password|credential|api[_-]?key|access[_-]?key|key)=)"
    r"(?P<value>[^&#\s]+)",
    re.IGNORECASE,
)


def redact_secret(value: object) -> str:
    """Return a stable, non-reversible display form for sensitive values."""

    text = str(value or "")
    if not text:
        return ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return "[redacted:%s]" % digest


def redact_text(value: object) -> str:
    """Remove common credential forms before text reaches an error or summary."""

    text = str(value or "")
    text = _SENSITIVE_QUERY_RE.sub(lambda match: "%s%s" % (match.group("name"), redact_secret(match.group("value"))), text)
    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: "%s%s%s" % (
            match.group("name"),
            match.group("separator"),
            redact_secret(match.group("value")),
        ),
        text,
    )


def redact_mapping(value: object) -> object:
    """Copy structured input while replacing credential-bearing fields."""

    if isinstance(value, Mapping):
        return {
            str(key): redact_secret(item) if _SENSITIVE_KEY_RE.search(str(key)) else redact_mapping(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_mapping(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def truncate_utf8(value: str, limit: int, *, suffix: str = "...") -> str:
    """Truncate by bytes without splitting a UTF-8 codepoint."""

    if limit < 1:
        raise ValueError("limit must be positive")
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    suffix_bytes = suffix.encode("utf-8")
    if len(suffix_bytes) >= limit:
        return suffix_bytes[:limit].decode("utf-8", errors="ignore")
    body = encoded[: limit - len(suffix_bytes)].decode("utf-8", errors="ignore")
    return body + suffix


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _first_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        candidate = _as_text(payload.get(key))
        if candidate:
            return redact_text(candidate)
    return ""


def _item_text(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("summary", "message", "title", "name", "symbol", "action", "reason"):
            candidate = _as_text(value.get(key))
            if candidate:
                return redact_text(candidate)
        return ""
    return redact_text(_as_text(value))


@dataclass(frozen=True)
class NotificationSummary:
    """A bounded, credential-safe representation of a domain event."""

    title: str
    content: str
    item_count: int


def build_notification_summary(event: DomainEvent, *, limit: int) -> NotificationSummary:
    """Build a compact report that never expands an event's arbitrary payload."""

    payload = dict(event.payload)
    title = _first_text(payload, "title", "portfolio_name", "portfolio", "name") or redact_text(event.event_type)
    overview = _first_text(payload, "summary", "message", "overview", "markdown", "content")
    raw_items = payload.get("changes") or payload.get("risks") or payload.get("items") or ()
    if not isinstance(raw_items, (list, tuple)):
        raw_items = ()
    items = [text for text in (_item_text(item) for item in raw_items) if text][:10]
    lines = [title]
    if overview:
        lines.append(overview)
    if items:
        lines.extend("- %s" % item for item in items)
        if len(raw_items) > len(items):
            lines.append("- %d additional changes omitted" % (len(raw_items) - len(items)))
    else:
        lines.append("No changes. Review the current data status and report.")
    data_status = _first_text(payload, "data_status", "quality_status", "status")
    if data_status:
        lines.append("Data: %s" % data_status)
    # Report links are deliberately sent to the target.  They are not returned
    # in DeliveryResult errors or diagnostic details.
    report_url = _as_text(payload.get("report_url") or payload.get("share_url"))
    if report_url:
        lines.append("Report: %s" % report_url)
    content = truncate_utf8("\n".join(lines), limit)
    return NotificationSummary(title=truncate_utf8(title, min(limit, 256)), content=content, item_count=len(items))


@dataclass(frozen=True)
class _TransportResponse:
    status_code: int
    body: object
    headers: Mapping[str, str]
    retry_after: Optional[float]


def _retry_after(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        parsed = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, IndexError):
        return None
    return max(0.0, (parsed - parsed.now(parsed.tzinfo)).total_seconds())


def _normalise_response(response: object) -> _TransportResponse:
    if isinstance(response, Mapping):
        status = response.get("status_code", response.get("status", 200))
        try:
            status_code = int(status)
        except (TypeError, ValueError):
            status_code = 500
        raw_headers = response.get("headers")
        headers = {str(key).lower(): str(value) for key, value in raw_headers.items()} if isinstance(raw_headers, Mapping) else {}
        body = response.get("json", response.get("body"))
        if body is None:
            body = {
                str(key): value
                for key, value in response.items()
                if key not in {"status", "status_code", "headers", "retry_after"}
            }
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (TypeError, ValueError):
                pass
        retry_after = _retry_after(response.get("retry_after"))
        if retry_after is None:
            retry_after = _retry_after(headers.get("retry-after"))
        return _TransportResponse(status_code=status_code, body=body, headers=headers, retry_after=retry_after)
    try:
        return _TransportResponse(status_code=int(response or 200), body={}, headers={}, retry_after=None)
    except (TypeError, ValueError):
        return _TransportResponse(status_code=500, body={}, headers={}, retry_after=None)


class _ChannelNotificationAdapter:
    """Shared delivery implementation for restricted external channels."""

    channel = "notification"
    content_limit = 3_900

    def __init__(self, endpoint: str, *, transport: Optional[NotificationTransport] = None, timeout: float = 5.0) -> None:
        endpoint = str(endpoint or "").strip()
        if not endpoint:
            raise ValueError("notification endpoint is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._endpoint = endpoint
        self._transport = transport
        self.timeout = float(timeout)

    @property
    def target_fingerprint(self) -> str:
        """A safe target identifier for target-health/audit records."""

        return redact_secret(self._endpoint)

    def _headers(self, event: DomainEvent) -> dict[str, str]:
        key = event.idempotency_key or event.event_id
        return {
            "Content-Type": "application/json",
            "Idempotency-Key": key,
            "X-Event-ID": event.event_id,
            "X-Notification-Channel": self.channel,
        }

    def _payload(self, event: DomainEvent, summary: NotificationSummary) -> Mapping[str, Any]:
        raise NotImplementedError

    def _provider_failure(self, body: object) -> tuple[str, bool] | None:
        return None

    def _provider_message_id(self, body: object) -> Optional[str]:
        if not isinstance(body, Mapping):
            return None
        for key in ("message_id", "msg_id", "request_id"):
            value = _as_text(body.get(key))
            if value:
                return redact_text(value)
        return None

    def _failure_result(self, event: DomainEvent, *, error: str, retryable: bool, status_code: Optional[int] = None, retry_after: Optional[float] = None) -> DeliveryResult:
        if retryable:
            return DeliveryResult.retryable_failure(
                redact_text(error),
                event_id=event.event_id,
                status_code=status_code,
                retry_after=retry_after,
            )
        return DeliveryResult.permanent_failure(
            redact_text(error),
            event_id=event.event_id,
            status_code=status_code,
        )

    def send(self, event: DomainEvent) -> DeliveryResult:
        summary = build_notification_summary(event, limit=self.content_limit)
        if self._transport is None:
            return self._failure_result(event, error="%s transport is not configured" % self.channel, retryable=False)
        try:
            response = self._transport(self._endpoint, self._payload(event, summary), self._headers(event), self.timeout)
        except RetryableDeliveryError as exc:
            return self._failure_result(event, error=str(exc), retryable=True)
        except PermanentDeliveryError as exc:
            return self._failure_result(event, error=str(exc), retryable=False)
        except (TimeoutError, ConnectionError, OSError) as exc:
            # The request may have reached the provider before the transport
            # failed.  Returning a retryable result would allow a duplicate
            # notification, so the decision delivery service freezes it as
            # ambiguous for manual reconciliation.
            raise AmbiguousDeliveryError(str(exc)) from exc
        except Exception as exc:
            return self._failure_result(event, error=str(exc), retryable=False)

        normalized = _normalise_response(response)
        if not 200 <= normalized.status_code < 300:
            retryable = normalized.status_code in {408, 425, 429} or normalized.status_code >= 500
            return self._failure_result(
                event,
                error="%s returned HTTP %d" % (self.channel, normalized.status_code),
                retryable=retryable,
                status_code=normalized.status_code,
                retry_after=normalized.retry_after,
            )
        provider_failure = self._provider_failure(normalized.body)
        if provider_failure is not None:
            error, retryable = provider_failure
            return self._failure_result(
                event,
                error=error,
                retryable=retryable,
                status_code=normalized.status_code,
                retry_after=normalized.retry_after,
            )
        return DeliveryResult(
            event_id=event.event_id,
            delivered=True,
            status_code=normalized.status_code,
            provider_message_id=self._provider_message_id(normalized.body),
            details={"channel": self.channel, "target": self.target_fingerprint, "items": summary.item_count},
        )


class WeComRobotNotificationAdapter(_ChannelNotificationAdapter):
    """Enterprise WeChat robot adapter using its markdown webhook schema."""

    channel = "wecom_robot"
    content_limit = 3_900

    def __init__(self, webhook_url: str, *, transport: Optional[NotificationTransport] = None, timeout: float = 5.0) -> None:
        super().__init__(webhook_url, transport=transport, timeout=timeout)

    def _payload(self, event: DomainEvent, summary: NotificationSummary) -> Mapping[str, Any]:
        return {"msgtype": "markdown", "markdown": {"content": summary.content}}

    def _provider_failure(self, body: object) -> tuple[str, bool] | None:
        if not isinstance(body, Mapping) or "errcode" not in body:
            return None
        try:
            code = int(body["errcode"])
        except (TypeError, ValueError):
            return ("wecom returned an invalid business code", False)
        if code == 0:
            return None
        return ("wecom rejected the message (code %d)" % code, code in {45009, 45011, 93000})


class PushPlusNotificationAdapter(_ChannelNotificationAdapter):
    """PushPlus adapter.  Its token enters only the outbound request body."""

    channel = "pushplus"
    content_limit = 9_000

    def __init__(self, token: str, *, transport: Optional[NotificationTransport] = None, timeout: float = 5.0, endpoint: str = "https://www.pushplus.plus/send") -> None:
        token = str(token or "").strip()
        if not token:
            raise ValueError("PushPlus token is required")
        self._token = token
        super().__init__(endpoint, transport=transport, timeout=timeout)

    def _payload(self, event: DomainEvent, summary: NotificationSummary) -> Mapping[str, Any]:
        return {"token": self._token, "title": summary.title, "content": summary.content, "template": "markdown"}

    def _provider_failure(self, body: object) -> tuple[str, bool] | None:
        if not isinstance(body, Mapping) or "code" not in body:
            return None
        try:
            code = int(body["code"])
        except (TypeError, ValueError):
            return ("PushPlus returned an invalid business code", False)
        if code in {0, 200}:
            return None
        return ("PushPlus rejected the message (code %d)" % code, code == 429 or code >= 500)


class FeishuRobotNotificationAdapter(_ChannelNotificationAdapter):
    """Feishu group-robot adapter using its text-message webhook schema."""

    channel = "feishu_robot"
    content_limit = 3_900

    def __init__(self, webhook_url: str, *, transport: Optional[NotificationTransport] = None, timeout: float = 5.0) -> None:
        super().__init__(webhook_url, transport=transport, timeout=timeout)

    def _payload(self, event: DomainEvent, summary: NotificationSummary) -> Mapping[str, Any]:
        return {"msg_type": "text", "content": {"text": summary.content}}

    def _provider_failure(self, body: object) -> tuple[str, bool] | None:
        if not isinstance(body, Mapping) or "code" not in body:
            return None
        try:
            code = int(body["code"])
        except (TypeError, ValueError):
            return ("Feishu returned an invalid business code", False)
        if code == 0:
            return None
        return ("Feishu rejected the message (code %d)" % code, code in {429, 90002, 90003} or code >= 500)


class QQOfficialBotNotificationAdapter(_ChannelNotificationAdapter):
    """QQ Official Bot adapter for a pre-authorized C2C or group endpoint.

    Token acquisition is intentionally outside this adapter.  The worker injects
    a protected, short-lived access token and the exact scoped message endpoint.
    """

    channel = "qq_official_bot"
    content_limit = 1_900

    def __init__(self, endpoint: str, *, app_id: str, access_token: str, transport: Optional[NotificationTransport] = None, timeout: float = 5.0) -> None:
        app_id = str(app_id or "").strip()
        access_token = str(access_token or "").strip()
        if not app_id or not access_token:
            raise ValueError("QQ app_id and access_token are required")
        self._app_id = app_id
        self._access_token = access_token
        super().__init__(endpoint, transport=transport, timeout=timeout)

    def _headers(self, event: DomainEvent) -> dict[str, str]:
        headers = super()._headers(event)
        headers["Authorization"] = "QQBot %s" % self._access_token
        headers["X-Union-Appid"] = self._app_id
        return headers

    def _payload(self, event: DomainEvent, summary: NotificationSummary) -> Mapping[str, Any]:
        return {"content": summary.content, "msg_type": 0, "msg_id": event.idempotency_key or event.event_id}

    def _provider_failure(self, body: object) -> tuple[str, bool] | None:
        if not isinstance(body, Mapping) or "code" not in body:
            return None
        try:
            code = int(body["code"])
        except (TypeError, ValueError):
            return ("QQ Official Bot returned an invalid business code", False)
        if code == 0:
            return None
        return ("QQ Official Bot rejected the message (code %d)" % code, code == 429 or code >= 500)


# Short names retain an obvious import path while keeping the product name explicit.
WeComNotificationAdapter = WeComRobotNotificationAdapter
FeishuNotificationAdapter = FeishuRobotNotificationAdapter
QQBotNotificationAdapter = QQOfficialBotNotificationAdapter


__all__ = [
    "FeishuNotificationAdapter",
    "FeishuRobotNotificationAdapter",
    "NotificationSummary",
    "NotificationTransport",
    "PushPlusNotificationAdapter",
    "QQBotNotificationAdapter",
    "QQOfficialBotNotificationAdapter",
    "WeComNotificationAdapter",
    "WeComRobotNotificationAdapter",
    "build_notification_summary",
    "redact_mapping",
    "redact_secret",
    "redact_text",
    "truncate_utf8",
]
