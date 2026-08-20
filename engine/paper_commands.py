"""Paper command types and enqueue helper for V2 durable command architecture."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from engine.execution_protocol import (
    Environment,
    OrderIntent,
    OrderIntentBatch,
    RiskDecision,
    ExecutionPermit,
    Side,
)
from engine.operations_store import CommandAcceptance, OperationsStore


def _serialize_for_json(obj: Any) -> Any:
    """Convert dataclass to JSON-serializable dict, handling Decimal and enums."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'value'):  # Enum
        return obj.value
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize_for_json(item) for item in obj]
    elif hasattr(obj, '__dataclass_fields__'):  # dataclass instance
        return _serialize_for_json(asdict(obj))
    else:
        return obj


@dataclass
class PaperStartPayload:
    """Payload for paper_start command."""

    account_id: str
    strategy_name: str
    codes: list[str]
    interval_seconds: int = 30
    initial_cash: float = 50_000.0
    params: dict[str, Any] | None = None
    custom_code: str | None = None


@dataclass
class PaperStopPayload:
    """Payload for paper_stop command."""

    account_id: str
    reason: str = "user_requested"


@dataclass
class PaperResetPayload:
    """Payload for paper_reset command."""

    account_id: str
    initial_cash: float = 50_000.0
    reason: str = "user_requested"


@dataclass
class PaperAdjustPositionPayload:
    """Payload for paper_adjust_position command."""

    account_id: str
    code: str
    direction: str
    volume: int


@dataclass
class ExecuteManualOrderPayload:
    """Payload for execute_manual_order command (V2 unified protocol)."""

    batch_dict: dict
    permit_dict: dict


class PaperCommandClient:
    """Client for enqueueing Paper commands into OperationsStore."""

    def __init__(self, operations_db: str | Path):
        self.store = OperationsStore(operations_db)

    def close(self) -> None:
        """Close the underlying store."""
        self.store.close()

    def enqueue_start(
        self,
        account_id: str,
        strategy_name: str,
        codes: list[str],
        interval_seconds: int = 30,
        initial_cash: float = 50_000.0,
        params: dict[str, Any] | None = None,
        custom_code: str | None = None,
        idempotency_key: str | None = None,
    ) -> CommandAcceptance:
        """Enqueue a paper_start command."""
        if not codes:
            raise ValueError("codes cannot be empty")
        if not account_id or "/" in account_id or "\\" in account_id:
            raise ValueError("invalid account_id")

        payload = {
            "account_id": account_id,
            "strategy_name": strategy_name,
            "codes": codes,
            "interval_seconds": interval_seconds,
            "initial_cash": initial_cash,
            "params": params,
            "custom_code": custom_code,
        }
        key = idempotency_key or f"paper_start_{account_id}_{strategy_name}"
        return self.store.accept_command(
            kind="paper_start",
            payload=payload,
            idempotency_key=key,
        )

    def enqueue_stop(
        self,
        account_id: str,
        reason: str = "user_requested",
        idempotency_key: str | None = None,
    ) -> CommandAcceptance:
        """Enqueue a paper_stop command."""
        payload = {
            "account_id": account_id,
            "reason": reason,
        }
        key = idempotency_key or f"paper_stop_{account_id}"
        return self.store.accept_command(
            kind="paper_stop",
            payload=payload,
            idempotency_key=key,
        )

    def enqueue_reset(
        self,
        account_id: str,
        initial_cash: float = 50_000.0,
        reason: str = "user_requested",
        idempotency_key: str | None = None,
    ) -> CommandAcceptance:
        """Enqueue a paper_reset command."""
        payload = {
            "account_id": account_id,
            "initial_cash": initial_cash,
            "reason": reason,
        }
        key = idempotency_key or f"paper_reset_{account_id}"
        return self.store.accept_command(
            kind="paper_reset",
            payload=payload,
            idempotency_key=key,
        )

    def enqueue_adjust_position(
        self,
        account_id: str,
        code: str,
        direction: str,
        volume: int,
        idempotency_key: str | None = None,
    ) -> CommandAcceptance:
        """Enqueue a paper_adjust_position command."""
        if direction not in {"buy", "sell"}:
            raise ValueError("direction must be buy or sell")
        payload = {
            "account_id": account_id,
            "code": code,
            "direction": direction,
            "volume": volume,
        }
        key = idempotency_key or f"paper_adjust_{account_id}_{code}_{direction}"
        return self.store.accept_command(
            kind="paper_adjust_position",
            payload=payload,
            idempotency_key=key,
        )

    def enqueue_manual_order(
        self,
        *,
        instrument: str,
        side: Side,
        quantity: int,
        execution_run_id: str,
        account_id: str,
        idempotency_key: str,
    ) -> CommandAcceptance:
        """Enqueue a manual order command (V2 unified protocol)."""
        intent = OrderIntent(
            instrument=instrument,
            side=side,
            quantity=quantity,
            execution_run_id=execution_run_id,
            account_id=account_id,
            environment=Environment.PAPER,
            idempotency_key=idempotency_key,
        )

        batch = OrderIntentBatch(
            batch_id=f"manual_{idempotency_key}",
            intents=[intent]
        )

        # 简化：手动订单默认全部批准，实际风控在 Worker 执行时检查
        decision = RiskDecision.from_batch(
            batch=batch,
            decision_id=f"decision_{idempotency_key}",
            policy_version="v2",
            status="approved",
            approved_intent_keys=[intent.idempotency_key],
            rejected_intent_keys=[],
            evaluated_at=datetime.now(timezone.utc),
        )

        permit = ExecutionPermit.from_decision(
            decision=decision,
            permit_id=f"permit_{idempotency_key}",
            fence_token="1",
            expires_at=datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
        )

        payload = {
            "batch_dict": _serialize_for_json(batch),
            "permit_dict": _serialize_for_json(permit),
        }

        return self.store.accept_command(
            kind="paper_execute_batch",
            payload=payload,
            idempotency_key=idempotency_key,
        )
