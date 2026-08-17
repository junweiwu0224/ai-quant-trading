"""Deterministic, evidence-bound research orchestration.

The public seam accepts one frozen :class:`ResearchContext`. Optional model
adapters can enrich the report, but they cannot introduce data that is absent
from that context. The deterministic result remains useful when a model fails.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from agentic.models import ResearchContext, ResearchJob, ResearchReport
from agentic.repository import AgenticRepository
from agentic.signal_validation import evaluate_signal_validation
from agentic.signals import SignalService

RESEARCH_ROLES = ("signal", "market", "theme", "bear", "decision")
PAPER_CANDIDATE_THRESHOLD = 0.6


class ResearchModelAdapter(Protocol):
    """Optional model seam; implementations receive only a frozen context."""

    def analyze(self, context: ResearchContext, deterministic_report: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ResearchPipeline:
    """Deep research module: context in, auditable job/report/signal out."""

    def __init__(
        self,
        repository: AgenticRepository,
        signal_service: SignalService | None = None,
        model_adapter: ResearchModelAdapter | Callable[[ResearchContext, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.repository = repository
        self.signal_service = signal_service or SignalService(repository)
        self.model_adapter = model_adapter

    def run(
        self,
        code: str,
        context: ResearchContext | Mapping[str, Any] | None = None,
        *,
        run_key: str | None = None,
        evidence_snapshot_id: str | None = None,
        publish_signal: bool = True,
    ) -> ResearchJob:
        frozen = context if isinstance(context, ResearchContext) else ResearchContext.from_mapping(
            code,
            context,
            evidence_snapshot_id=evidence_snapshot_id,
        )
        normalized_run_key = str(run_key or "").strip() or self.default_run_key(frozen)
        previous = self.repository.get_research_job_by_run_key(normalized_run_key)
        if previous is not None:
            return previous

        now = _utc_now_iso()
        deterministic = self._deterministic_report(frozen)
        report_payload = dict(deterministic)
        model_status = "deterministic"
        model_error = ""
        if self.model_adapter is not None:
            try:
                enrichment = self._call_model_adapter(frozen, deterministic)
                if isinstance(enrichment, Mapping):
                    report_payload = _merge_report(deterministic, enrichment)
                    model_status = "enriched"
            except Exception as exc:  # model failure must degrade, not erase facts
                model_status = "degraded"
                model_error = str(exc)

        report_payload["model_status"] = model_status
        if model_error:
            report_payload["model_error"] = model_error
        model_metadata = {
            **frozen.model_metadata,
            "adapter": type(self.model_adapter).__name__ if self.model_adapter is not None else "deterministic",
            "status": model_status,
        }
        report_payload["model_metadata"] = model_metadata
        if model_status == "degraded":
            report_payload["missing_fields"] = list(dict.fromkeys([*(report_payload.get("missing_fields") or []), "llm_enrichment"]))

        job_id = f"research_{uuid4().hex}"
        report_id = f"report_{uuid4().hex[:16]}"
        signal_id = None
        signal = None
        decision_signal: dict[str, Any] = {}
        if publish_signal:
            signal = self._build_decision_signal(
                frozen,
                report_payload,
                research_job_id=job_id,
                model_metadata=model_metadata,
            )
            signal_id = signal.id
            decision_signal = signal.decision_payload()

        # The signal is published before the report row so its append-only
        # ledger event can be retained even when report persistence is later
        # retried. Its research_job_id is already the deterministic job ID.

        report_payload["decision_signal"] = decision_signal
        report_payload["research_job_id"] = job_id
        report = ResearchReport(
            id=report_id,
            research_job_id=job_id,
            stock_code=frozen.stock_code,
            status="completed",
            summary=str(report_payload.get("summary") or report_payload.get("decision") or ""),
            roles=report_payload.get("roles") or {},
            decision_signal=decision_signal,
            evidence_snapshot_id=frozen.evidence_snapshot_id,
            data_quality=frozen.data_quality,
            missing_fields=frozen.missing_fields,
            source_health=frozen.source_health,
            model_metadata=model_metadata,
            created_at=now,
            updated_at=now,
        )
        report_dict = report.to_dict()
        # Keep the old final_report shape as a compatibility projection while
        # exposing the richer report/context as first-class fields.
        final_report = dict(report_payload)
        final_report.setdefault("code", frozen.stock_code)
        job = ResearchJob(
            id=job_id,
            code=frozen.stock_code,
            status="completed",
            roles=RESEARCH_ROLES,
            final_report=final_report,
            created_at=now,
            updated_at=now,
            run_key=normalized_run_key,
            context_id=frozen.id or f"context_{uuid4().hex[:16]}",
            report_id=report_id,
            decision_signal_id=signal_id,
            context=frozen.to_dict(),
            report=report_dict,
            decision_signal=decision_signal,
        )
        atomic_research_save = getattr(self.repository, "save_research_job_with_signal_atomically", None)
        if signal is not None and callable(atomic_research_save):
            atomic_research_save(job, signal)
        else:
            if signal is not None:
                self.signal_service.persist(signal)
            self.repository.save_research_job(job)
        return job

    @staticmethod
    def default_run_key(context: ResearchContext) -> str:
        payload = {
            "stock_code": context.stock_code,
            "as_of": context.as_of,
            "evidence_snapshot_id": context.evidence_snapshot_id,
            "market_phase": context.market_phase,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
        return f"research:{context.stock_code}:{digest}"

    def _call_model_adapter(self, context: ResearchContext, report: Mapping[str, Any]) -> Mapping[str, Any]:
        adapter = self.model_adapter
        if callable(adapter) and not hasattr(adapter, "analyze"):
            return adapter(context, report)
        return adapter.analyze(context, report)  # type: ignore[union-attr]

    def _deterministic_report(self, context: ResearchContext) -> dict[str, Any]:
        signal_engine = context.signal_engine
        used_legacy_score = "signal_score" not in signal_engine and "qlib_score" in signal_engine
        signal_score = _as_score(signal_engine.get("signal_score", signal_engine.get("qlib_score", 0.0)))
        validation = evaluate_signal_validation(signal_engine.get("signal_validation"))
        evidence_citable = context.evidence_status in {"citable", "ok"}
        data_ready = context.data_quality not in {"missing", "failed"}
        decision = "paper_candidate" if signal_score >= PAPER_CANDIDATE_THRESHOLD and validation.passed else "observe"
        action = _action_for_decision(decision, signal_score, validation.passed, evidence_citable, data_ready)
        missing_fields = list(context.missing_fields)
        if not context.evidence_snapshot_id:
            missing_fields.append("evidence_snapshot_id")
        if not context.technicals:
            missing_fields.append("technicals")
        if not context.fundamentals:
            missing_fields.append("fundamentals")
        if not data_ready:
            missing_fields.append("data_quality")
        missing_fields = list(dict.fromkeys(missing_fields))
        quality = context.data_quality
        if quality == "unknown":
            quality = "partial" if missing_fields else "complete"

        roles = {
            "signal": {
                "score": signal_score,
                "validation": {
                    "confidence": validation.confidence,
                    "sample_days": validation.sample_days,
                    "passed": validation.passed,
                    "label": validation.label,
                    "reason": validation.reason,
                },
            },
            "market": {
                "phase": context.market_phase,
                "summary": _summary(context.market_data, "market context unavailable"),
            },
            "theme": {
                "summary": _summary(context.themes, "unclassified"),
                "sentiment": _summary(context.sentiment, "sentiment unavailable"),
            },
            "bear": {
                "risk": _risk_note(context, validation),
                "missing_fields": missing_fields,
            },
            "decision": {
                "action": action,
                "rationale": _decision_rationale(decision, signal_score, validation),
            },
        }
        if used_legacy_score:
            input_aliases = {"qlib_score": "signal_score"}
        else:
            input_aliases = {}
        return {
            "code": context.stock_code,
            "as_of": context.as_of,
            "market_phase": context.market_phase,
            "decision": decision,
            "action": action,
            "signal_score": signal_score,
            "signal_validation": roles["signal"]["validation"],
            "data_quality": quality,
            "missing_fields": missing_fields,
            "evidence_snapshot_id": context.evidence_snapshot_id,
            "evidence_status": context.evidence_status,
            "source_health": dict(context.source_health),
            "roles": roles,
            "summary": roles["decision"]["rationale"],
            "input_aliases": input_aliases,
        }

    def _build_decision_signal(
        self,
        context: ResearchContext,
        report: Mapping[str, Any],
        *,
        research_job_id: str,
        model_metadata: Mapping[str, Any],
    ):
        validation = report["signal_validation"]
        score = float(report.get("signal_score") or 0.0)
        action = str(report.get("action") or "watch")
        direction = {"buy": "buy", "add": "buy", "sell": "sell", "reduce": "sell", "alert": "risk", "avoid": "risk"}.get(action, "hold")
        roles = report.get("roles") or {}
        risk = str((roles.get("bear") or {}).get("risk") or "风险边界待补充")
        reason = str((roles.get("decision") or {}).get("rationale") or report.get("summary") or "")
        return self.signal_service.build(
            agent_id="research_pipeline",
            source="daily_stock_analysis_absorbed",
            code=context.stock_code,
            direction=direction,
            confidence=float(validation.get("sample_days", 0) >= 20 and min(1.0, max(0.0, score)) or 0.35),
            time_horizon=str(context.signal_engine.get("horizon") or "3-10d"),
            entry_reasons=[reason or "研究报告生成的确定性结论"],
            risk_notes=[risk],
            suggested_position=float(context.position_risk.get("suggested_position") or 0.0),
            stop_loss=context.position_risk.get("stop_loss"),
            take_profit=context.position_risk.get("take_profit"),
            action=action,
            score=score,
            entry_low=context.position_risk.get("entry_low"),
            entry_high=context.position_risk.get("entry_high"),
            target_price=context.position_risk.get("target_price") or context.position_risk.get("take_profit"),
            invalidation=str(context.position_risk.get("invalidation") or ""),
            watch_conditions=context.position_risk.get("watch_conditions") or [],
            reason=reason,
            risk_summary=risk,
            catalyst_summary=str((roles.get("theme") or {}).get("summary") or ""),
            factor_contributions=context.technicals,
            evidence_snapshot_id=context.evidence_snapshot_id,
            research_job_id=research_job_id,
            data_quality=str(report.get("data_quality") or context.data_quality),
            missing_fields=list(report.get("missing_fields") or []),
            source_health=context.source_health,
            model_metadata=model_metadata,
        )


def _as_score(value: object) -> float:
    try:
        return min(1.0, max(0.0, float(value or 0.0)))
    except (TypeError, ValueError) as exc:
        raise ValueError("signal_score must be numeric") from exc


def _action_for_decision(decision: str, score: float, validated: bool, evidence_citable: bool, data_ready: bool) -> str:
    if decision == "paper_candidate" and evidence_citable and data_ready:
        return "buy"
    if score >= PAPER_CANDIDATE_THRESHOLD and not validated:
        return "watch"
    if not evidence_citable or not data_ready:
        return "alert"
    return "watch"


def _decision_rationale(decision: str, signal_score: float, signal_validation) -> str:
    if decision == "paper_candidate":
        return "signal_score meets paper threshold"
    if signal_score >= PAPER_CANDIDATE_THRESHOLD and not signal_validation.passed:
        return signal_validation.detail
    return "signal_score below paper threshold"


def _risk_note(context: ResearchContext, signal_validation) -> str:
    base = str(context.position_risk.get("risk") or "position sizing and stop-loss required")
    if signal_validation.passed:
        return base
    prefix = "AI验证样本不足" if signal_validation.reason == "AI signal validation sample is insufficient" else "AI未验证"
    return f"{prefix}；{base}"


def _summary(value: object, fallback: str) -> str:
    if isinstance(value, Mapping):
        for key in ("summary", "theme", "text", "name"):
            if value.get(key):
                return str(value[key])
        return fallback
    return str(value or fallback)


def _merge_report(base: Mapping[str, Any], enrichment: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in enrichment.items():
        if key == "roles" and isinstance(value, Mapping):
            roles = dict(merged.get("roles") or {})
            for role, role_value in value.items():
                roles[role] = {**(roles.get(role) or {}), **(dict(role_value) if isinstance(role_value, Mapping) else {"summary": role_value})}
            merged["roles"] = roles
        elif key not in {"evidence_snapshot_id", "data_quality", "missing_fields", "source_health"}:
            merged[key] = value
    return merged


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
