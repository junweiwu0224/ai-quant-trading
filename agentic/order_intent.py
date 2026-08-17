"""Paper-only order intent seam between promotion and execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional, Protocol

from .models import TradingSignal
from .promotion import PromotionDecision


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class PaperOrderIntent:
    id: str
    signal_id: str
    code: str
    direction: str
    order_type: str
    volume: int
    status: str
    reason: str
    created_at: str
    paper_only: bool = True
    confirmed_by: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {"buy", "sell"}:
            raise ValueError("paper order intent direction must be buy or sell")
        if self.order_type not in {"market", "limit"}:
            raise ValueError("unsupported order type: %s" % self.order_type)
        if self.status not in {"pending_confirmation", "confirmed", "paper_submitted", "rejected"}:
            raise ValueError("unsupported paper order intent status: %s" % self.status)
        if int(self.volume) <= 0 or int(self.volume) % 100 != 0:
            raise ValueError("paper order intent volume must be a positive board lot")
        if not self.paper_only:
            raise ValueError("live order intents are not supported by this module")
        object.__setattr__(self, "volume", int(self.volume))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


class PaperExecutionAdapter(Protocol):
    def submit(self, intent: PaperOrderIntent) -> PaperOrderIntent: ...


class InMemoryPaperExecutionAdapter:
    """Deterministic paper adapter; it cannot call a broker."""

    def __init__(self) -> None:
        self.submitted: List[PaperOrderIntent] = []

    def submit(self, intent: PaperOrderIntent) -> PaperOrderIntent:
        if intent.status != "confirmed":
            raise ValueError("paper submission requires a confirmed intent")
        submitted = replace(intent, status="paper_submitted")
        self.submitted.append(submitted)
        return submitted


class OrderIntentService:
    """Deep paper-intent module; live execution is deliberately absent."""

    def __init__(self, *, max_volume: Optional[int] = None, store=None) -> None:
        if max_volume is not None and (max_volume <= 0 or max_volume % 100 != 0):
            raise ValueError("max_volume must be a positive board lot")
        self.max_volume = max_volume
        self.store = store

    def _save(self, intent: PaperOrderIntent) -> PaperOrderIntent:
        if self.store is not None:
            self.store.save(intent)
        return intent

    def create(
        self,
        signal: TradingSignal,
        decision: PromotionDecision,
        *,
        volume: int,
        order_type: str = "limit",
        reason: str = "promotion approved for paper execution",
    ) -> PaperOrderIntent:
        if not decision.approved or decision.target != "paper_pending":
            raise ValueError("only an approved paper_pending decision can create an order intent")
        if signal.direction not in {"buy", "sell"}:
            raise ValueError("hold and risk signals cannot create order intents")
        if self.max_volume is not None and volume > self.max_volume:
            raise ValueError("paper order intent exceeds configured max_volume")
        return self._save(PaperOrderIntent(
            id="intent_%s" % uuid.uuid4().hex[:12],
            signal_id=signal.id,
            code=signal.code,
            direction=signal.direction,
            order_type=order_type,
            volume=volume,
            status="pending_confirmation",
            reason=reason,
            created_at=utc_now(),
            metadata={"promotion_policy_version": decision.policy_version},
        ))

    def confirm(self, intent: PaperOrderIntent, *, confirmed_by: str) -> PaperOrderIntent:
        if intent.status != "pending_confirmation":
            raise ValueError("only pending paper intents can be confirmed")
        if not confirmed_by.strip():
            raise ValueError("confirmed_by is required")
        return self._save(replace(intent, status="confirmed", confirmed_by=confirmed_by))

    def submit_to_paper(
        self,
        intent: PaperOrderIntent,
        adapter: Optional[PaperExecutionAdapter] = None,
    ) -> PaperOrderIntent:
        if adapter is None:
            adapter = InMemoryPaperExecutionAdapter()
        return self._save(adapter.submit(intent))
