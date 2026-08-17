"""Route immutable decision reports through explicit notification targets."""

from __future__ import annotations

import json
import hashlib
import os
import socket
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from engine.events.models import DomainEvent
from engine.events.outbox import SQLiteOutbox
from engine.notifications.models import DeliveryResult
from engine.notifications.channels import (
    FeishuRobotNotificationAdapter,
    PushPlusNotificationAdapter,
    QQOfficialBotNotificationAdapter,
    WeComRobotNotificationAdapter,
)

from .store import DecisionStore


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _secret_ref(value: str) -> str:
    if not value.startswith("env://"):
        return ""
    return os.getenv(value.removeprefix("env://"), "")


def _transport(endpoint: str, payload: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
    request = Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status_code": int(response.status), "body": body, "headers": dict(response.headers)}
    except HTTPError as exc:
        return {"status_code": exc.code, "body": exc.read().decode("utf-8", errors="replace"), "headers": dict(exc.headers or {})}
    except URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc


@dataclass
class DecisionDeliveryService:
    store: DecisionStore
    owner_id: str = ""
    outbox: SQLiteOutbox | None = None
    worker_owned: bool = False
    eligibility_check: Callable[[str, str], Mapping[str, Any]] | None = None
    fence_token_provider: Callable[[], str] | None = None
    fence_check: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if not self.owner_id:
            self.owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"

    def _fence_token(self) -> str:
        if self.fence_token_provider is None:
            return ""
        return str(self.fence_token_provider() or "")

    def _assert_fence(self) -> None:
        if self.fence_check is not None:
            self.fence_check()
        try:
            return str(self.fence_token_provider() or "")
        except Exception:
            return ""

    def _adapter(self, target: Mapping[str, Any]):
        config = target.get("config") or {}
        secret = _secret_ref(str(config.get("secret_ref") or ""))
        endpoint = _secret_ref(str(config.get("endpoint_ref") or ""))
        channel = str(target.get("channel") or "")
        if channel == "wecom_robot":
            return WeComRobotNotificationAdapter(endpoint, transport=_transport)
        if channel == "pushplus":
            return PushPlusNotificationAdapter(secret, transport=_transport, endpoint=endpoint or "https://www.pushplus.plus/send")
        if channel == "feishu_robot":
            return FeishuRobotNotificationAdapter(endpoint, transport=_transport)
        if channel == "qq_official_bot":
            app_id = os.getenv("QQ_BOT_APP_ID", "")
            return QQOfficialBotNotificationAdapter(endpoint, app_id=app_id, access_token=secret, transport=_transport)
        raise ValueError("unsupported_notification_channel")

    @staticmethod
    def _event(report: Mapping[str, Any], event_type: str, report_url: str) -> DomainEvent:
        body = report.get("body") or {}
        all_decisions = [item for item in list(body.get("decisions") or []) if isinstance(item, Mapping)]
        decisions = [item for item in all_decisions if DecisionDeliveryService._relevant(item, event_type)]
        changes = [{"symbol": item.get("symbol"), "action": item.get("action"), "summary": "%s: %s" % (item.get("symbol"), item.get("action"))} for item in decisions[:10]]
        trigger = str(body.get("trigger") or "")
        run_key = str(body.get("run_key") or "")
        # New reports persist the complete scheduling context.  ``slot`` and
        # trigger parsing remain only for reports created before that contract
        # was added.
        slot = str(body.get("schedule_slot") or body.get("slot") or "")
        if not slot and trigger.startswith("scheduled_prepare:"):
            slot = trigger.removeprefix("scheduled_prepare:")
        trade_date = str(body.get("trade_date") or "")
        if not trade_date and run_key:
            # Prepared run keys are deliberately stable and end in the local
            # trade date.  Keep parsing conservative so a malformed legacy key
            # cannot manufacture an apparently valid date.
            candidate = run_key.rsplit(":", 1)[-1]
            if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-":
                trade_date = candidate
        portfolio_id = str(body.get("portfolio_id") or report.get("decision_run_id") or "")
        version_id = str(body.get("portfolio_version_id") or "")
        facts = sorted(
            [
                {
                    "membership_id": str(item.get("membership_id") or ""),
                    "symbol": str(item.get("symbol") or ""),
                    "action": str(item.get("action") or ""),
                    "confirming_bar_end": str(item.get("confirming_bar_end") or ""),
                }
                for item in decisions
            ],
            key=lambda item: (item["membership_id"], item["action"], item["confirming_bar_end"], item["symbol"]),
        )
        key_material = {
            "portfolio_id": portfolio_id,
            "slot": slot,
            "trade_date": trade_date,
            "portfolio_version_id": version_id,
            "event_type": event_type,
            "run_key": run_key,
            "members": facts,
            "report_hash": str(report.get("report_hash") or ""),
        }
        event_key = "decision:" + hashlib.sha256(
            json.dumps(key_material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        summary = (
            "%d 个标的发生动作变化" % len(decisions)
            if decisions
            else "组合当前无动作变化"
        )
        return DomainEvent.create(
            "decision.report.%s" % event_type,
            portfolio_id,
            {
                "title": "策略组合决策摘要",
                "summary": summary,
                "changes": changes,
                "total_count": len(all_decisions),
                "data_status": body.get("quality_status", "unknown"),
                "report_url": report_url,
                "report_id": report.get("id"),
                "report_hash": report.get("report_hash"),
                "portfolio_id": portfolio_id,
                "portfolio_version_id": version_id,
                "slot": slot,
                "trade_date": trade_date,
                "members": facts,
            },
            idempotency_key=event_key,
        )

    @staticmethod
    def _relevant(decision: Mapping[str, Any], event_type: str) -> bool:
        action = str(decision.get("action") or "")
        previous = decision.get("previous_action")
        if event_type == "scheduled":
            return action == "major_risk" and previous != "major_risk" or (
                previous is not None and previous != action
            )
        if event_type == "major_risk":
            return action == "major_risk" and previous != "major_risk"
        if event_type == "state_change":
            return bool(decision.get("confirmed")) and previous is not None and previous != action and action != "major_risk"
        return False

    def _deliver_event(self, workspace_id: str, report_id: str, event: DomainEvent) -> list[dict[str, Any]]:
        if not self.worker_owned:
            raise RuntimeError("decision delivery is Worker-owned")
        report = self.store.get_report(workspace_id, report_id)
        if not report:
            raise KeyError("report_not_found")
        portfolio_id = str((report.get("body") or {}).get("portfolio_id") or "")
        event_type = event.event_type.removeprefix("decision.report.")
        if self.fence_check is not None:
            self.fence_check()
        if self.eligibility_check is not None:
            eligibility = self.eligibility_check(workspace_id, portfolio_id)
            if self.fence_check is not None:
                self.fence_check()
            if not bool(eligibility.get("eligible")):
                return [{
                    "status": "blocked_eligibility",
                    "error": "automatic_delivery_eligibility_lost",
                    "reasons": list(eligibility.get("reasons") or []),
                }]
        routes = [item for item in self.store.list_routes(workspace_id, portfolio_id) if item.get("event_type") == event_type and item.get("enabled")]
        if not event.payload.get("changes") and event_type != "scheduled":
            return []
        attempts = []
        if not routes:
            return [{"status": "blocked_no_route", "error": "notification_route_not_configured"}]
        for route in routes:
            target = self.store.get_target(workspace_id, route["target_id"])
            if not target:
                attempts.append({"status": "blocked_target", "error": "notification_target_not_found"})
                continue
            if not target.get("enabled"):
                self._assert_fence()
                attempts.append(self.store.record_delivery_attempt(workspace_id, report_id, target["id"], "%s:%s" % (event.idempotency_key, target["id"]), "blocked_target", error="notification_target_disabled"))
                continue
            key = "%s:%s" % (event.idempotency_key, target["id"])
            if target.get("test_status") != "passed":
                self._assert_fence()
                attempts.append(self.store.record_delivery_attempt(workspace_id, report_id, target["id"], key, "blocked_target", error="notification_target_not_tested"))
                continue
            if not _enabled("DECISION_EXTERNAL_DELIVERY_ENABLED"):
                self._assert_fence()
                attempts.append(self.store.record_delivery_attempt(workspace_id, report_id, target["id"], key, "blocked_external", error="external_delivery_not_enabled"))
                continue
            self._assert_fence()
            fence_token = self._fence_token()
            claim = self.store.claim_delivery(
                workspace_id,
                report_id,
                target["id"],
                key,
                self.owner_id,
                fence_token=fence_token,
            )
            if not claim.get("claimed"):
                attempts.append(claim.get("attempt") or claim)
                continue
            request_started = False
            try:
                self._assert_fence()
                # Adapter construction is local validation only.  A malformed
                # secret reference or endpoint must remain retryable; only the
                # send call below crosses the external-request boundary.
                adapter = self._adapter(target)
                self._assert_fence()
                # From this point onward the provider may have accepted the
                # request even if the local process later times out or loses
                # its lease.  Such failures are ambiguous, never automatic
                # retries.
                request_started = True
                result = adapter.send(event)
                self._assert_fence()
                status = "delivered" if result.delivered else ("retryable" if result.retryable else "failed")
                attempts.append(self.store.record_delivery_attempt(
                    workspace_id,
                    report_id,
                    target["id"],
                    key,
                    status,
                    error=result.error or "",
                    response_summary=str(dict(result.details)),
                    claim_owner_id=self.owner_id,
                    fence_token=fence_token,
                ))
                attempts[-1]["retry_after"] = result.retry_after
                claim_status = "delivered" if result.delivered else ("available" if result.retryable else "dead")
                if not self.store.complete_delivery_claim(
                    key,
                    target["id"],
                    self.owner_id,
                    claim_status,
                    fence_token=fence_token,
                ):
                    raise RuntimeError("delivery_claim_fence_lost")
            except Exception as exc:
                try:
                    self._assert_fence()
                except Exception:
                    # A stale Worker must not make an ambiguous key available
                    # to its replacement.  The claim itself is the durable
                    # operator-visible marker when the fence is already lost;
                    # no untrusted synthetic success is recorded.
                    if request_started:
                        self.store.mark_delivery_claim_unknown(
                            key,
                            target["id"],
                            self.owner_id,
                            fence_token=fence_token,
                        )
                    raise
                if request_started:
                    attempts.append(self.store.record_delivery_attempt(
                        workspace_id,
                        report_id,
                        target["id"],
                        key,
                        "unknown",
                        error=str(exc),
                        claim_owner_id=self.owner_id,
                        fence_token=fence_token,
                    ))
                    if not self.store.complete_delivery_claim(
                        key,
                        target["id"],
                        self.owner_id,
                        "unknown",
                        fence_token=fence_token,
                    ):
                        raise RuntimeError("delivery_claim_fence_lost")
                else:
                    # No provider request was started, so the key is safe to
                    # retry after a local preflight failure.
                    self.store.complete_delivery_claim(
                        key,
                        target["id"],
                        self.owner_id,
                        "available",
                        fence_token=fence_token,
                    )
        return attempts

    def deliver_report(self, workspace_id: str, report_id: str, event_type: str, *, report_url: str = "") -> list[dict[str, Any]]:
        """Worker-only compatibility entry point for controlled replay."""

        if not self.worker_owned:
            raise RuntimeError("direct report delivery is disabled outside Worker")
        report = self.store.get_report(workspace_id, report_id)
        if not report:
            raise KeyError("report_not_found")
        return self._deliver_event(workspace_id, report_id, self._event(report, event_type, report_url))

    def enqueue_report(self, workspace_id: str, report_id: str, event_type: str, *, report_url: str = "") -> str | None:
        """Persist a report event; only the Worker may perform external I/O."""

        if self.outbox is None or not self.worker_owned:
            raise RuntimeError("decision delivery outbox is required for enqueue")
        report = self.store.get_report(workspace_id, report_id)
        if not report:
            raise KeyError("report_not_found")
        event = self._event(report, event_type, report_url)
        if not event.payload.get("changes") and event_type != "scheduled":
            return None
        event_payload = dict(event.payload)
        event_payload["workspace_id"] = workspace_id
        event = DomainEvent.create(
            event.event_type,
            event.aggregate_id,
            event_payload,
            idempotency_key=event.idempotency_key,
            occurred_at=event.occurred_at,
        )
        return self.outbox.publish(event)

    def test_target(self, workspace_id: str, target_id: str) -> dict[str, Any]:
        """Run a target health check under the Worker ownership fence."""

        if not self.worker_owned:
            raise RuntimeError("direct target tests are disabled outside Worker")
        self._assert_fence()
        target = self.store.get_target(workspace_id, target_id)
        if not target:
            raise KeyError("target_not_found")
        if not _enabled("DECISION_EXTERNAL_DELIVERY_ENABLED"):
            return {"status": "external_test_required", "message": "外部投递未获启用，未发送测试消息"}
        event = DomainEvent.create(
            "decision.target.test",
            target_id,
            {"title": "AI Quant 渠道测试", "summary": "这是一次受控渠道健康检查", "changes": []},
            idempotency_key="target-test:%s" % target_id,
        )
        try:
            result = self._adapter(target).send(event)
            self._assert_fence()
            status = "passed" if result.delivered else "failed"
            updated = self.store.mark_target_test(workspace_id, target_id, status)
            return {"status": status, "target": updated, "error": result.error, "retry_after": result.retry_after}
        except Exception as exc:
            # Do not write a target health result after ownership is lost.
            self._assert_fence()
            updated = self.store.mark_target_test(workspace_id, target_id, "failed")
            return {"status": "failed", "target": updated, "error": str(exc)}


class DecisionOutboxDispatcher:
    """Worker-owned dispatcher for report events and per-target attempts."""

    event_types = (
        "decision.report.scheduled",
        "decision.report.state_change",
        "decision.report.major_risk",
    )

    def __init__(self, outbox: SQLiteOutbox, service: DecisionDeliveryService, *, consumer: str = "decision-report-delivery") -> None:
        self.outbox = outbox
        self.service = service
        self.consumer = consumer

    def dispatch(self, *, limit: int = 20, now=None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for message in self.outbox.claim(consumer=self.consumer, limit=limit, now=now, event_types=self.event_types):
            payload = dict(message.event.payload)
            workspace_id = str(payload.get("workspace_id") or "")
            report_id = str(payload.get("report_id") or "")
            try:
                attempts = self.service._deliver_event(workspace_id, report_id, message.event)
                self.service._assert_fence()
                retryable = any(item.get("status") == "retryable" for item in attempts)
                deferred = any(
                    str(item.get("status")) in {"blocked_no_route", "blocked_target", "blocked_external", "blocked_eligibility"}
                    for item in attempts
                )
                failed = any(str(item.get("status")) in {"failed", "dead"} for item in attempts)
                unknown = any(str(item.get("status")) in {"unknown", "dispatching"} for item in attempts)
                retry_afters = [float(item["retry_after"]) for item in attempts if item.get("status") == "retryable" and item.get("retry_after") is not None]
                if retryable:
                    self.outbox.mark_failed(message.event.event_id, consumer=self.consumer, claim_token=message.claim_token or "", error="one or more notification targets need retry", retryable=True, retry_after=min(retry_afters) if retry_afters else None, now=now)
                elif deferred:
                    self.outbox.defer(message.event.event_id, consumer=self.consumer, claim_token=message.claim_token or "", reason="one or more notification targets are policy-blocked", now=now)
                elif unknown:
                    self.outbox.mark_failed(message.event.event_id, consumer=self.consumer, claim_token=message.claim_token or "", error="provider outcome is ambiguous; manual review required", retryable=False, now=now)
                elif failed:
                    self.outbox.mark_failed(message.event.event_id, consumer=self.consumer, claim_token=message.claim_token or "", error="one or more notification targets failed permanently", retryable=False, now=now)
                else:
                    self.outbox.mark_delivered(message.event.event_id, consumer=self.consumer, claim_token=message.claim_token or "")
                results.append({"event_id": message.event.event_id, "attempts": attempts, "status": "unknown" if unknown else ("pending" if retryable or deferred else ("dead" if failed else "processed"))})
            except Exception as exc:
                self.service._assert_fence()
                self.outbox.mark_failed(message.event.event_id, consumer=self.consumer, claim_token=message.claim_token or "", error=str(exc), retryable=True, now=now)
                results.append({"event_id": message.event.event_id, "status": "retryable", "error": str(exc)})
        return results

    def test_target(self, workspace_id: str, target_id: str) -> dict[str, Any]:
        return self.service.test_target(workspace_id, target_id)


__all__ = ["DecisionDeliveryService", "DecisionOutboxDispatcher"]
