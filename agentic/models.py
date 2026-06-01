from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

SignalDirection = Literal["buy", "sell", "hold", "risk"]
SignalStatus = Literal[
    "new",
    "watching",
    "backtested",
    "paper_pending",
    "paper_active",
    "expired",
    "invalidated",
    "closed",
]

VALID_SIGNAL_DIRECTIONS = {"buy", "sell", "hold", "risk"}
VALID_SIGNAL_STATUSES = {
    "new",
    "watching",
    "backtested",
    "paper_pending",
    "paper_active",
    "expired",
    "invalidated",
    "closed",
}

_CODE_PATTERNS = (
    re.compile(r"^(?:SH|SZ|BJ)?(?P<code>\d{6})(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE),
)


def normalize_signal_code(code: str) -> str:
    raw = str(code or "").strip()
    for pattern in _CODE_PATTERNS:
        match = pattern.fullmatch(raw)
        if match:
            return match.group("code")
    raise ValueError("stock code must be a 6-digit A-share code with optional SH/SZ/BJ prefix or suffix")


def _as_float(name: str, value: float | int | str) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    return converted


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    kind: str
    description: str
    permissions: tuple[str, ...] | list[str] = field(default_factory=tuple)
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", tuple(self.permissions))


@dataclass(frozen=True)
class TradingSignal:
    id: str
    agent_id: str
    source: str
    code: str
    direction: SignalDirection
    confidence: float
    time_horizon: str
    entry_reasons: tuple[str, ...] | list[str]
    risk_notes: tuple[str, ...] | list[str]
    suggested_position: float
    stop_loss: float | None
    take_profit: float | None
    status: SignalStatus
    created_at: str
    expires_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_code = normalize_signal_code(self.code)
        confidence = _as_float("confidence", self.confidence)
        suggested_position = _as_float("suggested_position", self.suggested_position)
        stop_loss = None if self.stop_loss is None else _as_float("stop_loss", self.stop_loss)
        take_profit = None if self.take_profit is None else _as_float("take_profit", self.take_profit)
        entry_reasons = tuple(self.entry_reasons or ())
        risk_notes = tuple(self.risk_notes or ())

        if self.direction not in VALID_SIGNAL_DIRECTIONS:
            raise ValueError(f"unsupported signal direction: {self.direction}")
        if self.status not in VALID_SIGNAL_STATUSES:
            raise ValueError(f"unsupported signal status: {self.status}")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not entry_reasons:
            raise ValueError("entry_reasons is required")
        if not risk_notes:
            raise ValueError("risk_notes is required")
        if not 0 <= suggested_position <= 1:
            raise ValueError("suggested_position must be between 0 and 1")
        if stop_loss is not None and not 0 < stop_loss <= 1:
            raise ValueError("stop_loss must be in (0, 1]")
        if take_profit is not None and take_profit <= 0:
            raise ValueError("take_profit must be positive")

        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "suggested_position", suggested_position)
        object.__setattr__(self, "stop_loss", stop_loss)
        object.__setattr__(self, "take_profit", take_profit)
        object.__setattr__(self, "entry_reasons", entry_reasons)
        object.__setattr__(self, "risk_notes", risk_notes)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class ResearchJob:
    id: str
    code: str
    status: str
    roles: tuple[str, ...] | list[str]
    final_report: dict
    created_at: str
    updated_at: str
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_signal_code(self.code))
        object.__setattr__(self, "roles", tuple(self.roles or ()))
        object.__setattr__(self, "final_report", dict(self.final_report or {}))


@dataclass(frozen=True)
class PaperStrategyCandidate:
    id: str
    candidate_id: str
    name: str
    dsl: dict
    sample: dict
    metrics: dict
    promotion: dict
    status: str
    requires_confirmation: bool
    created_at: str

    def __post_init__(self) -> None:
        if self.status not in {"paper_candidate", "paper_active", "rejected"}:
            raise ValueError(f"unsupported paper strategy candidate status: {self.status}")
        if not self.candidate_id:
            raise ValueError("candidate_id is required")
        object.__setattr__(self, "dsl", dict(self.dsl or {}))
        object.__setattr__(self, "sample", dict(self.sample or {}))
        object.__setattr__(self, "metrics", dict(self.metrics or {}))
        object.__setattr__(self, "promotion", dict(self.promotion or {}))
        object.__setattr__(self, "requires_confirmation", bool(self.requires_confirmation))
