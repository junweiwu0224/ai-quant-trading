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


def normalize_signal_code(code: str) -> str:
    cleaned = re.sub(r"[^0-9]", "", code or "")
    if len(cleaned) < 6:
        raise ValueError("stock code must contain 6 digits")
    return cleaned[-6:]


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    kind: str
    description: str
    permissions: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=True)
class TradingSignal:
    id: str
    agent_id: str
    source: str
    code: str
    direction: SignalDirection
    confidence: float
    time_horizon: str
    entry_reasons: list[str]
    risk_notes: list[str]
    suggested_position: float
    stop_loss: float | None
    take_profit: float | None
    status: SignalStatus
    created_at: str
    expires_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_signal_code(self.code))
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.entry_reasons:
            raise ValueError("entry_reasons is required")
        if not self.risk_notes:
            raise ValueError("risk_notes is required")
        if not 0 <= float(self.suggested_position) <= 1:
            raise ValueError("suggested_position must be between 0 and 1")
