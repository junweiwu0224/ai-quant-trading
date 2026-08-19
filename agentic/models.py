from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

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
DecisionAction = Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"]
VALID_DECISION_ACTIONS = {"buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"}
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


def _optional_float(name: str, value: object) -> float | None:
    if value is None or value == "":
        return None
    return _as_float(name, value)  # type: ignore[arg-type]


def _decision_action_for_direction(direction: SignalDirection) -> DecisionAction:
    return {
        "buy": "buy",
        "sell": "sell",
        "hold": "hold",
        "risk": "alert",
    }[direction]


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    kind: str
    description: str
    permissions: tuple[str, ...] | list[str] = field(default_factory=tuple)
    enabled: bool = True
    legacy_alias_for: str = ""

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
    # Structured Decision Signal fields extend the legacy lifecycle projection.
    action: DecisionAction | str | None = None
    score: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    target_price: float | None = None
    invalidation: str = ""
    watch_conditions: tuple[str, ...] | list[str] = field(default_factory=tuple)
    reason: str = ""
    risk_summary: str = ""
    catalyst_summary: str = ""
    factor_contributions: dict[str, Any] = field(default_factory=dict)
    evidence_snapshot_id: str | None = None
    research_job_id: str | None = None
    data_quality: str = "unknown"
    missing_fields: tuple[str, ...] | list[str] = field(default_factory=tuple)
    source_health: dict[str, Any] = field(default_factory=dict)
    model_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_code = normalize_signal_code(self.code)
        confidence = _as_float("confidence", self.confidence)
        suggested_position = _as_float("suggested_position", self.suggested_position)
        stop_loss = None if self.stop_loss is None else _as_float("stop_loss", self.stop_loss)
        take_profit = None if self.take_profit is None else _as_float("take_profit", self.take_profit)
        score = _optional_float("score", self.score)
        entry_low = _optional_float("entry_low", self.entry_low)
        entry_high = _optional_float("entry_high", self.entry_high)
        target_price = _optional_float("target_price", self.target_price)
        entry_reasons = tuple(self.entry_reasons or ())
        risk_notes = tuple(self.risk_notes or ())
        watch_conditions = tuple(str(item) for item in (self.watch_conditions or ()) if str(item).strip())
        missing_fields = tuple(str(item) for item in (self.missing_fields or ()) if str(item).strip())
        action = str(self.action or "").strip().lower()

        if self.direction not in VALID_SIGNAL_DIRECTIONS:
            raise ValueError(f"unsupported signal direction: {self.direction}")
        if not action:
            action = _decision_action_for_direction(self.direction)
        if self.status not in VALID_SIGNAL_STATUSES:
            raise ValueError(f"unsupported signal status: {self.status}")
        if action not in VALID_DECISION_ACTIONS:
            raise ValueError(f"unsupported decision action: {action}")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if score is not None and not 0 <= score <= 1:
            raise ValueError("score must be between 0 and 1")
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
        if entry_low is not None and entry_low <= 0:
            raise ValueError("entry_low must be positive")
        if entry_high is not None and entry_high <= 0:
            raise ValueError("entry_high must be positive")
        if entry_low is not None and entry_high is not None and entry_low > entry_high:
            raise ValueError("entry_low must not exceed entry_high")
        if target_price is not None and target_price <= 0:
            raise ValueError("target_price must be positive")

        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "suggested_position", suggested_position)
        object.__setattr__(self, "stop_loss", stop_loss)
        object.__setattr__(self, "take_profit", take_profit)
        object.__setattr__(self, "entry_reasons", entry_reasons)
        object.__setattr__(self, "risk_notes", risk_notes)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "entry_low", entry_low)
        object.__setattr__(self, "entry_high", entry_high)
        object.__setattr__(self, "target_price", target_price)
        object.__setattr__(self, "watch_conditions", watch_conditions)
        object.__setattr__(self, "missing_fields", missing_fields)
        object.__setattr__(self, "factor_contributions", dict(self.factor_contributions or {}))
        object.__setattr__(self, "source_health", dict(self.source_health or {}))
        object.__setattr__(self, "model_metadata", dict(self.model_metadata or {}))

    @property
    def horizon(self) -> str:
        """DSA-compatible name for the existing time_horizon field."""

        return self.time_horizon

    @property
    def legacy_direction(self) -> SignalDirection:
        return self.direction

    def decision_payload(self) -> dict[str, Any]:
        """Return the structured Decision Signal projection for storage/API use."""

        return {
            "action": self.action,
            "score": self.score,
            "confidence": self.confidence,
            "horizon": self.horizon,
            "entry_low": self.entry_low,
            "entry_high": self.entry_high,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "invalidation": self.invalidation,
            "watch_conditions": list(self.watch_conditions),
            "reason": self.reason,
            "risk_summary": self.risk_summary,
            "catalyst_summary": self.catalyst_summary,
            "factor_contributions": dict(self.factor_contributions),
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "research_job_id": self.research_job_id,
            "data_quality": self.data_quality,
            "missing_fields": list(self.missing_fields),
            "source_health": dict(self.source_health),
            "model_metadata": dict(self.model_metadata),
            "legacy_direction": self.legacy_direction,
        }


# The system has one signal lifecycle. This alias gives research callers a
# domain name without introducing a second projection or transition machine.
DecisionSignal = TradingSignal


@dataclass(frozen=True)
class ResearchContext:
    """Frozen, auditable inputs accepted by a research run."""

    stock_code: str
    as_of: str
    market: str = "A"
    market_phase: str = "unknown"
    market_data: dict[str, Any] = field(default_factory=dict)
    technicals: dict[str, Any] = field(default_factory=dict)
    fundamentals: dict[str, Any] = field(default_factory=dict)
    money_flow: dict[str, Any] = field(default_factory=dict)
    sentiment: dict[str, Any] = field(default_factory=dict)
    themes: dict[str, Any] = field(default_factory=dict)
    macro: dict[str, Any] = field(default_factory=dict)
    evidence_snapshot_id: str | None = None
    evidence_status: str = "unknown"
    evidence_window: dict[str, Any] = field(default_factory=dict)
    source_health: dict[str, Any] = field(default_factory=dict)
    missing_fields: tuple[str, ...] | list[str] = field(default_factory=tuple)
    data_quality: str = "unknown"
    signal_engine: dict[str, Any] = field(default_factory=dict)
    position_risk: dict[str, Any] = field(default_factory=dict)
    model_metadata: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "stock_code", normalize_signal_code(self.stock_code))
        object.__setattr__(self, "missing_fields", tuple(str(item) for item in (self.missing_fields or ()) if str(item).strip()))
        for name in (
            "market_data", "technicals", "fundamentals", "money_flow", "sentiment",
            "themes", "macro", "evidence_window", "source_health", "signal_engine",
            "position_risk", "model_metadata", "budget",
        ):
            object.__setattr__(self, name, dict(getattr(self, name) or {}))

    @classmethod
    def from_mapping(
        cls,
        stock_code: str,
        values: Mapping[str, Any] | None = None,
        *,
        as_of: str | None = None,
        evidence_snapshot_id: str | None = None,
    ) -> "ResearchContext":
        payload = dict(values or {})
        nested = payload.get("research_context")
        if isinstance(nested, Mapping):
            merged = dict(payload)
            merged.update(dict(nested))
            payload = merged
        now = datetime_now_iso()
        return cls(
            stock_code=stock_code,
            as_of=str(payload.get("as_of") or as_of or now),
            market=str(payload.get("market") or "A"),
            market_phase=str(payload.get("market_phase") or "unknown"),
            market_data=payload.get("market_data") or payload.get("market_context") or {},
            technicals=payload.get("technicals") or payload.get("technical") or {},
            fundamentals=payload.get("fundamentals") or payload.get("fundamental") or {},
            money_flow=payload.get("money_flow") or payload.get("capital_flow") or {},
            sentiment=payload.get("sentiment") or {},
            themes=(
                payload.get("themes")
                or ({"theme": payload.get("theme")} if payload.get("theme") else {})
            ),
            macro=payload.get("macro") or {},
            evidence_snapshot_id=payload.get("evidence_snapshot_id") or evidence_snapshot_id,
            evidence_status=str(payload.get("evidence_status") or "unknown"),
            evidence_window=payload.get("evidence_window") or {},
            source_health=payload.get("source_health") or {},
            missing_fields=payload.get("missing_fields") or (),
            data_quality=str(payload.get("data_quality") or "unknown"),
            signal_engine=payload.get("signal_engine") or {
                key: payload[key] for key in ("signal_score", "qlib_score", "signal_validation") if key in payload
            },
            position_risk=payload.get("position_risk") or {},
            model_metadata=payload.get("model_metadata") or {},
            budget=payload.get("budget") or {},
            id=str(payload.get("context_id") or payload.get("id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "stock_code": self.stock_code,
            "as_of": self.as_of,
            "market": self.market,
            "market_phase": self.market_phase,
            "market_data": dict(self.market_data),
            "technicals": dict(self.technicals),
            "fundamentals": dict(self.fundamentals),
            "money_flow": dict(self.money_flow),
            "sentiment": dict(self.sentiment),
            "themes": dict(self.themes),
            "macro": dict(self.macro),
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "evidence_status": self.evidence_status,
            "evidence_window": dict(self.evidence_window),
            "source_health": dict(self.source_health),
            "missing_fields": list(self.missing_fields),
            "data_quality": self.data_quality,
            "signal_engine": dict(self.signal_engine),
            "position_risk": dict(self.position_risk),
            "model_metadata": dict(self.model_metadata),
            "budget": dict(self.budget),
        }


@dataclass(frozen=True)
class ResearchReport:
    """Structured report projection; prose is secondary to its references."""

    id: str
    research_job_id: str
    stock_code: str
    status: str
    summary: str
    roles: dict[str, Any] = field(default_factory=dict)
    decision_signal: dict[str, Any] = field(default_factory=dict)
    evidence_snapshot_id: str | None = None
    data_quality: str = "unknown"
    missing_fields: tuple[str, ...] | list[str] = field(default_factory=tuple)
    source_health: dict[str, Any] = field(default_factory=dict)
    model_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "stock_code", normalize_signal_code(self.stock_code))
        object.__setattr__(self, "roles", dict(self.roles or {}))
        object.__setattr__(self, "decision_signal", dict(self.decision_signal or {}))
        object.__setattr__(self, "missing_fields", tuple(str(item) for item in (self.missing_fields or ()) if str(item).strip()))
        object.__setattr__(self, "source_health", dict(self.source_health or {}))
        object.__setattr__(self, "model_metadata", dict(self.model_metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "research_job_id": self.research_job_id,
            "stock_code": self.stock_code,
            "status": self.status,
            "summary": self.summary,
            "roles": dict(self.roles),
            "decision_signal": dict(self.decision_signal),
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "data_quality": self.data_quality,
            "missing_fields": list(self.missing_fields),
            "source_health": dict(self.source_health),
            "model_metadata": dict(self.model_metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def datetime_now_iso() -> str:
    # Kept local to avoid making the models module depend on the pipeline.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


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
    run_key: str | None = None
    context_id: str | None = None
    report_id: str | None = None
    decision_signal_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)
    decision_signal: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_signal_code(self.code))
        object.__setattr__(self, "roles", tuple(self.roles or ()))
        object.__setattr__(self, "final_report", dict(self.final_report or {}))
        object.__setattr__(self, "context", dict(self.context or {}))
        object.__setattr__(self, "report", dict(self.report or {}))
        object.__setattr__(self, "decision_signal", dict(self.decision_signal or {}))


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


@dataclass(frozen=True)
class PaperStrategyExecution:
    id: str
    candidate_record_id: str
    candidate_id: str
    name: str
    dsl: dict
    codes: tuple[str, ...] | list[str]
    status: str
    reason: str
    requires_confirmation: bool
    created_at: str

    def __post_init__(self) -> None:
        if self.status not in {"paper_intent_pending", "paper_intent_confirmed", "paper_orders_submitted", "rejected"}:
            raise ValueError(f"unsupported paper strategy execution status: {self.status}")
        if not self.candidate_record_id:
            raise ValueError("candidate_record_id is required")
        codes = tuple(str(code) for code in (self.codes or ()))
        object.__setattr__(self, "codes", codes)
        object.__setattr__(self, "dsl", dict(self.dsl or {}))
        object.__setattr__(self, "requires_confirmation", bool(self.requires_confirmation))


@dataclass(frozen=True)
class AgenticPaperOrderDraft:
    id: str
    execution_id: str
    code: str
    direction: str
    order_type: str
    volume: int
    status: str
    strategy_name: str
    signal_reason: str
    created_at: str

    def __post_init__(self) -> None:
        if self.direction not in {"buy", "sell"}:
            raise ValueError(f"unsupported draft direction: {self.direction}")
        if self.order_type not in {"market", "limit"}:
            raise ValueError(f"unsupported draft order_type: {self.order_type}")
        if self.status not in {"draft_pending", "submitted", "rejected"}:
            raise ValueError(f"unsupported draft status: {self.status}")
        if int(self.volume) <= 0 or int(self.volume) % 100 != 0:
            raise ValueError("draft volume must be a positive board lot")
        object.__setattr__(self, "volume", int(self.volume))
