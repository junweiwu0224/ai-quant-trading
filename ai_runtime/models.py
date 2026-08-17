"""Stable contracts for the AI runtime.

These models intentionally do not contain an executable decision action.  A
report can explain research evidence, but it cannot become a decision merely
by being persisted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class GenerationErrorCode(str, Enum):
    BACKEND_NOT_CONFIGURED = "backend_not_configured"
    BACKEND_NOT_INSTALLED = "backend_not_installed"
    UNSAFE_CONFIG = "unsafe_config"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    EMPTY_OUTPUT = "empty_output"
    COMMAND_NOT_FOUND = "command_not_found"
    NON_ZERO_EXIT = "non_zero_exit"
    UNKNOWN = "unknown_backend_error"


class GenerationError(Exception):
    """Normalized provider failure which is safe to persist and display."""

    def __init__(
        self,
        code: GenerationErrorCode,
        message: str,
        *,
        provider: str = "",
        model: str = "",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.details = details or {}
        super().__init__(message)

    def public_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": str(self),
            "provider": self.provider,
            "model": self.model,
            "retryable": self.retryable,
            "details": self.details,
        }


class GenerationUsage(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    provider: str
    model: str
    backend: str = "openai_compatible"
    usage: GenerationUsage = Field(default_factory=GenerationUsage)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ProviderChannel(BaseModel):
    """Persistable provider configuration; only a secret reference is allowed."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    protocol: Literal["openai_compatible", "litellm", "local_cli"] = "openai_compatible"
    base_url: str = ""
    model: str = ""
    secret_ref: str = ""
    command: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = 100
    retries: int = Field(default=0, ge=0, le=3)
    timeout_seconds: float = Field(default=45.0, gt=0, le=600)
    supports_json: bool = True
    supports_stream: bool = True

    @field_validator("secret_ref")
    @classmethod
    def validate_secret_ref(cls, value: str) -> str:
        clean = str(value or "").strip()
        if clean and not clean.startswith("env://"):
            raise ValueError("secret_ref must use env://NAME")
        return clean


class AnalysisContext(BaseModel):
    """Immutable input snapshot supplied to one AI task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    market: str = Field(min_length=1, max_length=16)
    instrument: str = Field(min_length=1, max_length=64)
    as_of: str = ""
    blocks: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    quality_status: Literal["available", "partial", "missing", "stale", "failed", "unknown"] = "unknown"
    source: str = "provided_snapshot"
    context_hash: str = Field(min_length=64, max_length=64)


class RoleOutput(BaseModel):
    """Strict role output.  ``action`` is intentionally not a legal field."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=40)
    conclusion: str = Field(min_length=1, max_length=4000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=6000)
    common_evidence: list[str] = Field(default_factory=list, max_length=20)
    disagreements: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    next_checks: list[str] = Field(default_factory=list, max_length=20)


class DSAReviewOnlyModel(BaseModel):
    """Common marker for DSA-compatible blocks shown only to a human."""

    model_config = ConfigDict(extra="forbid")

    review_only: Literal[True] = True
    authority: Literal["human_review_only"] = "human_review_only"


class DSAPositionAdvice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    no_position: str | None = Field(default=None, max_length=1000)
    has_position: str | None = Field(default=None, max_length=1000)


class DSACoreConclusion(DSAReviewOnlyModel):
    one_sentence: str | None = Field(default=None, max_length=2000)
    signal_type: str | None = Field(default=None, max_length=120)
    time_sensitivity: str | None = Field(default=None, max_length=120)
    position_advice: DSAPositionAdvice | None = None


class DSATrendStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ma_alignment: str | None = Field(default=None, max_length=300)
    is_bullish: bool | None = None
    trend_score: int | float | str | None = None


class DSAPricePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_price: int | float | str | None = None
    ma5: int | float | str | None = None
    ma10: int | float | str | None = None
    ma20: int | float | str | None = None
    bias_ma5: int | float | str | None = None
    bias_status: str | None = Field(default=None, max_length=200)
    support_level: int | float | str | None = None
    resistance_level: int | float | str | None = None


class DSAVolumeAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volume_ratio: int | float | str | None = None
    volume_status: str | None = Field(default=None, max_length=200)
    turnover_rate: int | float | str | None = None
    volume_meaning: str | None = Field(default=None, max_length=1000)


class DSAChipStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profit_ratio: int | float | str | None = None
    avg_cost: int | float | str | None = None
    concentration: int | float | str | None = None
    chip_health: str | None = Field(default=None, max_length=200)


class DSADataPerspective(DSAReviewOnlyModel):
    trend_status: DSATrendStatus | None = None
    price_position: DSAPricePosition | None = None
    volume_analysis: DSAVolumeAnalysis | None = None
    chip_structure: DSAChipStructure | None = None


class DSAIntelligence(DSAReviewOnlyModel):
    latest_news: str | None = Field(default=None, max_length=3000)
    risk_alerts: list[str] = Field(default_factory=list, max_length=20)
    positive_catalysts: list[str] = Field(default_factory=list, max_length=20)
    earnings_outlook: str | None = Field(default=None, max_length=1500)
    sentiment_summary: str | None = Field(default=None, max_length=1500)


class DSASniperPoints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ideal_buy: int | float | str | None = None
    secondary_buy: int | float | str | None = None
    stop_loss: int | float | str | None = None
    take_profit: int | float | str | None = None


class DSAPositionStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_position: str | None = Field(default=None, max_length=500)
    entry_plan: str | None = Field(default=None, max_length=1500)
    risk_control: str | None = Field(default=None, max_length=1500)


class DSABattlePlan(DSAReviewOnlyModel):
    sniper_points: DSASniperPoints | None = None
    position_strategy: DSAPositionStrategy | None = None
    action_checklist: list[str] = Field(default_factory=list, max_length=20)


class DSAPhaseDecision(DSAReviewOnlyModel):
    phase_context: dict[str, Any] = Field(default_factory=dict)
    action_window: str | None = Field(default=None, max_length=200)
    immediate_action: str | None = Field(default=None, max_length=1000)
    watch_conditions: list[str] = Field(default_factory=list, max_length=20)
    next_check_time: str | None = Field(default=None, max_length=120)
    confidence_reason: str | None = Field(default=None, max_length=1500)
    data_limitations: list[str] = Field(default_factory=list, max_length=20)


class DSASignalAttribution(DSAReviewOnlyModel):
    technical_indicators: int | float | str | None = None
    news_sentiment: int | float | str | None = None
    fundamentals: int | float | str | None = None
    market_conditions: int | float | str | None = None
    strongest_bullish_signal: str | None = Field(default=None, max_length=1000)
    strongest_bearish_signal: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def normalize_contributions(self) -> "DSASignalAttribution":
        fields = ("technical_indicators", "news_sentiment", "fundamentals", "market_conditions")
        values: dict[str, float | None] = {}
        for name in fields:
            value = getattr(self, name)
            if isinstance(value, str):
                normalized = value.strip().replace("%", "")
                if normalized.upper() in {"", "N/A", "NULL", "NONE"}:
                    value = None
                else:
                    try:
                        value = float(normalized)
                    except ValueError:
                        value = None
            try:
                numeric = float(value) if value is not None else None
            except (TypeError, ValueError):
                numeric = None
            values[name] = numeric if numeric is not None and math.isfinite(numeric) else None
            if values[name] is not None:
                values[name] = max(0.0, min(100.0, values[name]))
        if all(value is not None for value in values.values()):
            total = sum(value for value in values.values() if value is not None)
            if total > 0:
                normalized_values = {name: round((value or 0) * 100 / total) for name, value in values.items()}
                difference = 100 - sum(normalized_values.values())
                first_non_zero = next((name for name in fields if normalized_values[name] > 0), fields[0])
                normalized_values[first_non_zero] += difference
                values = {name: float(value) for name, value in normalized_values.items()}
        for name, value in values.items():
            setattr(self, name, value)
        return self


class DSAAgentOpinion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1, max_length=80)
    stance: Literal["bullish", "neutral", "bearish", "unknown"] = "unknown"
    confidence: float | None = Field(default=None, ge=0, le=1)


class DSAAgentDisagreementExplanation(DSAReviewOnlyModel):
    base_opinions: list[DSAAgentOpinion] = Field(default_factory=list, max_length=20)
    risk_control_summary: str | None = Field(default=None, max_length=1500)
    degraded_events: list[str] = Field(default_factory=list, max_length=20)
    data_quality: str | None = Field(default=None, max_length=500)
    decision_path: str = Field(default="仅供人工复核，不形成可执行指令", max_length=2000)


_DSA_PROJECTION_MODELS: dict[str, type[BaseModel]] = {
    "core_conclusion": DSACoreConclusion,
    "data_perspective": DSADataPerspective,
    "intelligence": DSAIntelligence,
    "battle_plan": DSABattlePlan,
    "phase_decision": DSAPhaseDecision,
    "signal_attribution": DSASignalAttribution,
    "agent_disagreement_explanation": DSAAgentDisagreementExplanation,
}

_PROJECTION_FORBIDDEN_FIELDS = {
    "action",
    "actions",
    "order",
    "orders",
    "buy",
    "sell",
    "trade",
    "execute",
    "execution",
    "place_order",
}


def _safe_projection_value(value: Any, *, depth: int = 0) -> Any:
    """Keep allowlisted report blocks small and remove executable-looking keys."""

    if depth > 6:
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _safe_projection_value(child, depth=depth + 1)
            for key, child in value.items()
            if str(key).strip().lower() not in _PROJECTION_FORBIDDEN_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_projection_value(item, depth=depth + 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value[:4000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:400]


def project_dsa_blocks(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project reference-report blocks into a safe, typed AI report surface.

    The reference project calls this group ``dashboard``.  The projection is
    intentionally allowlisted and every returned block is explicitly marked
    human-review-only.  Invalid blocks are omitted instead of being persisted
    as untyped provider output.
    """

    if not isinstance(raw, Mapping):
        return {}
    source = raw.get("dashboard") if isinstance(raw.get("dashboard"), Mapping) else raw
    projected: dict[str, Any] = {}
    for name, model in _DSA_PROJECTION_MODELS.items():
        candidate = source.get(name)
        if not isinstance(candidate, Mapping):
            continue
        try:
            projected[name] = model.model_validate(_safe_projection_value(candidate)).model_dump(mode="json")
        except ValidationError:
            continue
    return projected


class AIReport(BaseModel):
    """Structured, non-authoritative report artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "ai-report.v1"
    profile: str
    status: Literal["complete", "partial", "degraded", "unavailable"]
    authoritative: Literal[False] = False
    decision_effect: Literal["none"] = "none"
    market: str
    instrument: str
    context_hash: str
    quality_status: str
    opinions: list[RoleOutput] = Field(default_factory=list)
    synthesis: SynthesisOutput | None = None
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    core_conclusion: DSACoreConclusion | None = None
    data_perspective: DSADataPerspective | None = None
    intelligence: DSAIntelligence | None = None
    battle_plan: DSABattlePlan | None = None
    phase_decision: DSAPhaseDecision | None = None
    signal_attribution: DSASignalAttribution | None = None
    agent_disagreement_explanation: DSAAgentDisagreementExplanation | None = None


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


DEFAULT_AGENT_ROLES: tuple[str, ...] = (
    "technical",
    "intelligence",
    "quant",
    "risk",
    "decision",
)


ROLE_BRIEFS: dict[str, str] = {
    "technical": "评估趋势、量价、波动、指标和结构，只引用输入快照。",
    "intelligence": "评估公告、新闻、资金与情绪证据；缺数据时明确写 unknown。",
    "quant": "评估因子口径、样本、回测、成本和过拟合风险；不创造回测结果。",
    "risk": "评估数据质量、流动性、集中度、回撤和执行风险；不下达交易动作。",
    "decision": "综合可验证研究观点，指出需要补充的证据；不得返回 buy/sell/order/action 字段。",
}
