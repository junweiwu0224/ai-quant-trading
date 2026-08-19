"""Validated durable commands accepted by the Paper control plane."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from engine.operations_store import CommandAcceptance, OperationsStore


PAPER_COMMAND_KINDS = frozenset({"paper.start", "paper.stop", "paper.reset"})
_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class PaperCommandValidationError(ValueError):
    """Raised when a Paper command cannot be accepted safely."""


def normalize_account_id(value: str) -> str:
    account_id = str(value or "").strip()
    if not _ACCOUNT_ID.fullmatch(account_id):
        raise PaperCommandValidationError("account_id must be a single path-safe identifier")
    return account_id


def _text(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PaperCommandValidationError(f"{field} must not be empty")
    return text


def _codes(values: list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise PaperCommandValidationError("codes must be a non-empty list")
    normalized = [_text(value, "code") for value in values]
    if not normalized:
        raise PaperCommandValidationError("codes must be a non-empty list")
    if len(normalized) != len(set(normalized)):
        raise PaperCommandValidationError("codes must be unique")
    return sorted(normalized)


def _positive_number(value: int | float, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value <= 0:
        raise PaperCommandValidationError(f"{field} must be positive and finite")
    return value


@dataclass(frozen=True)
class PaperCommandService:
    """Small command producer; it never constructs or runs ``PaperEngine``."""

    store: OperationsStore

    def enqueue_start(
        self,
        *,
        idempotency_key: str,
        account_id: str = "paper-default",
        strategy: str = "dual_ma",
        codes: list[str] | tuple[str, ...],
        interval_seconds: int = 30,
        initial_cash: float = 50_000,
        params: Mapping[str, Any] | None = None,
        custom_code: str | None = None,
    ) -> CommandAcceptance:
        if not isinstance(interval_seconds, int) or isinstance(interval_seconds, bool) or interval_seconds <= 0:
            raise PaperCommandValidationError("interval_seconds must be a positive integer")
        if params is not None and not isinstance(params, Mapping):
            raise PaperCommandValidationError("params must be a mapping")
        if isinstance(params, Mapping) and params.get("enable_risk") is False:
            raise PaperCommandValidationError("Paper commands cannot disable risk")
        if custom_code is not None and not isinstance(custom_code, str):
            raise PaperCommandValidationError("custom_code must be text")
        payload = {
            "account_id": normalize_account_id(account_id),
            "strategy": _text(strategy, "strategy"),
            "codes": _codes(codes),
            "interval_seconds": interval_seconds,
            "initial_cash": _positive_number(initial_cash, "initial_cash"),
            "params": dict(params or {}),
            "custom_code": custom_code,
            "enable_risk": True,
        }
        return self.store.accept_command(
            idempotency_key=_text(idempotency_key, "idempotency_key"),
            kind="paper.start",
            payload=payload,
        )

    def enqueue_stop(
        self,
        *,
        idempotency_key: str,
        account_id: str = "paper-default",
        reason: str = "operator_request",
    ) -> CommandAcceptance:
        return self._simple("paper.stop", idempotency_key, account_id, reason)

    def enqueue_reset(
        self,
        *,
        idempotency_key: str,
        account_id: str = "paper-default",
        reason: str = "operator_request",
    ) -> CommandAcceptance:
        return self._simple("paper.reset", idempotency_key, account_id, reason)

    def _simple(self, kind: str, idempotency_key: str, account_id: str, reason: str) -> CommandAcceptance:
        if kind not in PAPER_COMMAND_KINDS:
            raise PaperCommandValidationError(f"unsupported Paper command: {kind}")
        return self.store.accept_command(
            idempotency_key=_text(idempotency_key, "idempotency_key"),
            kind=kind,
            payload={"account_id": normalize_account_id(account_id), "reason": _text(reason, "reason")},
        )


__all__ = [
    "PAPER_COMMAND_KINDS",
    "PaperCommandService",
    "PaperCommandValidationError",
    "normalize_account_id",
]
