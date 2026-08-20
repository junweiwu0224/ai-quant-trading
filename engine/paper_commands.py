"""Paper command types and enqueue helper for V2 durable command architecture."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.operations_store import CommandAcceptance, OperationsStore


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
