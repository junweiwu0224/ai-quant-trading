"""Pure deterministic scoring and state-transition rules for decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

ACTIONS = (
    "buy_candidate",
    "watch",
    "hold",
    "reduce_candidate",
    "major_risk",
    "stale",
    "decision_invalid",
)
ORDINARY_ACTIONS = ACTIONS[:4]


@dataclass(frozen=True)
class StrategyContribution:
    strategy_name: str
    strategy_version: str
    normalized_score: float
    confidence: float
    data_quality: float
    configured_weight: float
    effective_weight: float
    contribution: float
    reason_codes: tuple[str, ...] = ()
    risk_veto: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "normalized_score": self.normalized_score,
            "confidence": self.confidence,
            "data_quality": self.data_quality,
            "configured_weight": self.configured_weight,
            "effective_weight": self.effective_weight,
            "contribution": self.contribution,
            "reason_codes": list(self.reason_codes),
            "risk_veto": self.risk_veto,
        }


@dataclass(frozen=True)
class DecisionEvaluation:
    action: str
    score: float | None
    valid: bool
    stale: bool
    risk_veto: bool
    reason_codes: tuple[str, ...]
    contributions: tuple[StrategyContribution, ...]
    previous_action: str | None = None
    confirmed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "score": self.score,
            "valid": self.valid,
            "stale": self.stale,
            "risk_veto": self.risk_veto,
            "reason_codes": list(self.reason_codes),
            "contributions": [item.as_dict() for item in self.contributions],
            "previous_action": self.previous_action,
            "confirmed": self.confirmed,
        }


def _bounded(value: Any, low: float, high: float, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(low, min(high, number))


def _reason_codes(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, Iterable):
        return ()
    return tuple(str(item) for item in value if str(item))


def _risk_evidence_valid(raw: Mapping[str, Any]) -> bool:
    """Require an auditable reason before accepting a score-less veto.

    A veto may intentionally omit ordinary score fields, but a bare boolean is
    not evidence.  Existing strategy adapters expose a non-empty reason code;
    newer adapters may provide a structured ``risk_evidence`` object instead.
    """

    if raw.get("risk_evidence_valid") is True:
        return True
    evidence = raw.get("risk_evidence")
    if isinstance(evidence, Mapping):
        if evidence.get("valid") is False:
            return False
        if evidence.get("reason") or evidence.get("rule") or evidence.get("source"):
            return True
    return bool(_reason_codes(raw.get("reason_codes")))


def score_strategy_outputs(
    outputs: Iterable[Mapping[str, Any]],
    weights: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
) -> DecisionEvaluation:
    """Score normalized strategy outputs without performing any I/O.

    Risk-veto strategies bypass the weighted average. A missing/invalid score,
    or a zero effective-weight denominator, produces ``decision_invalid``.
    """
    if not isinstance(weights, Mapping):
        weights = {
            str(item.get("strategy_name", "")): item
            for item in weights
            if item.get("strategy_name")
        }
    contributions: list[StrategyContribution] = []
    reasons: list[str] = []
    risk_veto = False
    invalid_required_output = False
    total = 0.0
    weighted_score = 0.0

    enabled_configs = {
        str(name): dict(config)
        for name, config in weights.items()
        if str(name) and isinstance(config, Mapping) and bool(config.get("enabled", True))
    }

    def _weight(config: Mapping[str, Any]) -> float:
        value = _bounded(config.get("weight", 0), 0, math.inf, 0.0)
        return value or 0.0

    normal_total = sum(
        _weight(config)
        for config in enabled_configs.values()
        if not bool(config.get("is_risk_veto", False))
    )
    normal_weights = {
        name: (_weight(config) / normal_total if normal_total > 0 else 0.0)
        for name, config in enabled_configs.items()
        if not bool(config.get("is_risk_veto", False))
    }
    seen_outputs: set[str] = set()

    for raw in outputs:
        strategy_name = str(raw.get("strategy_name") or raw.get("name") or "").strip()
        if not strategy_name:
            reasons.append("missing_strategy_name")
            continue
        configured = enabled_configs.get(strategy_name, {})
        enabled = bool(configured.get("enabled", False))
        if not enabled:
            continue
        if strategy_name in seen_outputs:
            reasons.append("duplicate_strategy_output:%s" % strategy_name)
            invalid_required_output = True
            continue
        seen_outputs.add(strategy_name)
        raw_risk_veto = bool(raw.get("risk_veto", False))
        # A veto is a safety outcome, not a weighted score.  Providers may
        # therefore omit ordinary scoring fields when they can still prove the
        # veto condition.  Keep a deterministic zero-valued contribution for
        # the audit trail and let evaluate_decision suppress it when the input
        # itself is stale or invalid.
        score = _bounded(raw.get("normalized_score"), 0, 100)
        confidence = _bounded(raw.get("confidence"), 0, 1)
        quality = _bounded(raw.get("data_quality"), 0, 1)
        if raw_risk_veto and not _risk_evidence_valid(raw):
            reasons.append(f"risk_evidence_missing:{strategy_name}")
            invalid_required_output = True
            continue
        if raw_risk_veto:
            score = 0.0 if score is None else score
            confidence = 1.0 if confidence is None else confidence
            quality = 1.0 if quality is None else quality
        configured_weight = (
            _weight(configured)
            if bool(configured.get("is_risk_veto", False))
            else normal_weights.get(strategy_name, 0.0)
        )
        is_veto = raw_risk_veto or bool(configured.get("is_risk_veto", False))
        item_reasons = _reason_codes(raw.get("reason_codes"))
        if score is None or confidence is None or quality is None:
            reasons.append(f"invalid_input:{strategy_name}")
            invalid_required_output = True
            continue
        if raw_risk_veto:
            risk_veto = True
        effective = configured_weight if is_veto else configured_weight * confidence * quality
        contribution = score * effective
        item = StrategyContribution(
            strategy_name=strategy_name,
            strategy_version=str(raw.get("strategy_version") or configured.get("version") or ""),
            normalized_score=score,
            confidence=confidence,
            data_quality=quality,
            configured_weight=configured_weight,
            effective_weight=effective,
            contribution=contribution,
            reason_codes=item_reasons,
            risk_veto=is_veto,
        )
        contributions.append(item)
        if not is_veto:
            total += effective
            weighted_score += contribution

    missing = sorted(set(enabled_configs) - seen_outputs)
    if missing:
        invalid_required_output = True
        reasons.extend("missing_strategy_output:%s" % name for name in missing)

    if risk_veto:
        reasons.append("risk_veto")
        return DecisionEvaluation("major_risk", None, True, False, True, tuple(dict.fromkeys(reasons)), tuple(contributions))
    if invalid_required_output:
        reasons.append("required_strategy_invalid")
    if invalid_required_output or total <= 0:
        reasons.append("zero_effective_weight")
        return DecisionEvaluation("decision_invalid", None, False, False, False, tuple(dict.fromkeys(reasons)), tuple(contributions))
    score = max(0.0, min(100.0, weighted_score / total))
    return DecisionEvaluation(
        action=classify_score(score),
        score=score,
        valid=True,
        stale=False,
        risk_veto=False,
        reason_codes=tuple(dict.fromkeys(reasons)),
        contributions=tuple(contributions),
    )


def classify_score(score: float) -> str:
    if score >= 70:
        return "buy_candidate"
    if score >= 55:
        return "watch"
    if score >= 40:
        return "hold"
    return "reduce_candidate"


def transition_action(
    previous_action: str | None,
    score: float | None,
    *,
    risk_veto: bool = False,
    stale: bool = False,
    invalid: bool = False,
) -> str:
    """Apply risk, invalid/stale and 5-point hysteresis in deterministic order."""
    if risk_veto:
        return "major_risk"
    if invalid:
        return "decision_invalid"
    if stale:
        # A stale input cannot invent a new action. Keep the last valid state
        # visible until the data either recovers or becomes explicitly invalid.
        if previous_action and previous_action not in {"stale", "decision_invalid"}:
            return previous_action
        return "stale"
    if score is None:
        return "decision_invalid"
    target = classify_score(score)
    if previous_action not in ORDINARY_ACTIONS:
        return target
    if previous_action == "buy_candidate":
        return "buy_candidate" if score >= 65 else "watch"
    if previous_action == "watch":
        if score >= 75:
            return "buy_candidate"
        if score < 50:
            return "hold"
        return "watch"
    if previous_action == "hold":
        if score >= 60:
            return "watch"
        if score < 35:
            return "reduce_candidate"
        return "hold"
    if score >= 45:
        return "hold"
    return "reduce_candidate"


def evaluate_decision(
    outputs: Iterable[Mapping[str, Any]],
    weights: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    *,
    previous_action: str | None = None,
    data_stale: bool = False,
    data_invalid: bool = False,
    invalid_pending: bool = False,
    confirmed: bool = False,
) -> DecisionEvaluation:
    scored = score_strategy_outputs(outputs, weights)
    # A risk veto is actionable only while the risk input itself is usable.
    # Stale or invalid data must never turn an old bar into an immediate alert.
    effective_risk_veto = scored.risk_veto and not data_stale and not data_invalid
    reasons = list(scored.reason_codes)
    if scored.risk_veto and not effective_risk_veto:
        reasons.append("risk_veto_suppressed_by_data_quality")
    action = transition_action(
        previous_action,
        scored.score,
        risk_veto=effective_risk_veto,
        stale=data_stale,
        invalid=data_invalid or (not scored.valid and not data_stale and not invalid_pending),
    )
    if data_stale:
        reasons.append("stale_data")
    if data_invalid:
        reasons.append("invalid_data")
    if invalid_pending:
        reasons.append("invalid_data_pending_recovery")

    # Intraday callers must pass the two-bar confirmation. Preserve the last
    # action while a candidate transition is still provisional; first state
    # creation remains an auditable observation but is never a change event.
    if (
        not confirmed
        and action != previous_action
        and previous_action is not None
        and action in ACTIONS
        and previous_action not in {"decision_invalid", "stale"}
    ):
        action = previous_action
        reasons.append("awaiting_two_bar_confirmation")

    return DecisionEvaluation(
        action=action,
        score=scored.score,
        valid=scored.valid and not data_invalid and not invalid_pending,
        stale=data_stale or invalid_pending,
        risk_veto=effective_risk_veto,
        reason_codes=tuple(dict.fromkeys(reasons)),
        contributions=scored.contributions,
        previous_action=previous_action,
        confirmed=confirmed,
    )


def _bar_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def confirm_completed_bars(bars: Iterable[Mapping[str, Any]], action: str | None = None) -> bool:
    """Return true only for two ordered, adjacent, completed 5-minute bars."""
    items = list(bars)
    if len(items) < 2:
        return False
    last_two = items[-2:]
    if any(
        not bool(item.get("completed", False))
        or bool(item.get("revision", False))
        or bool(item.get("revised", False))
        or bool(item.get("missing", False))
        or bool(item.get("provider_revision", False))
        for item in last_two
    ):
        return False
    if action and any(item.get("action") != action for item in last_two):
        return False
    first = _bar_time(last_two[0].get("bar_end"))
    second = _bar_time(last_two[1].get("bar_end"))
    if first is None or second is None or second <= first:
        return False
    return (second - first).total_seconds() == 300
