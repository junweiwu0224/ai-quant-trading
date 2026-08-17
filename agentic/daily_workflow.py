"""Deterministic daily vertical slice: evidence to signal to notification."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Any, Mapping
from typing import List, Optional, Sequence, Tuple

from data.evidence.models import EvidenceItem, EvidenceLink, EvidenceSnapshot, EvidenceSource, utc_now
from data.evidence.store import EvidenceStore
from engine.events.models import DomainEvent
from engine.events.outbox import SQLiteOutbox

from .promotion import PromotionContext, PromotionDecision, PromotionPolicy
from .models import ResearchContext
from .research_pipeline import ResearchPipeline
from .repository import AgenticRepository
from .signal_ledger import SignalLedger


@dataclass(frozen=True)
class SignalCandidate:
    signal_id: str
    symbol: str
    from_status: Optional[str]
    target: str
    context: PromotionContext


@dataclass(frozen=True)
class PromotionResult:
    signal_id: str
    decision: PromotionDecision
    ledger_event_id: Optional[str] = None


@dataclass(frozen=True)
class DailyBrief:
    snapshot_id: str
    captured_at: str
    watchlist: Tuple[str, ...]
    evidence_count: int
    promotions: Tuple[PromotionResult, ...]
    event_id: str
    research_jobs: Tuple[str, ...] = ()
    report_count: int = 0
    markdown: str = ""
    run_key: str = ""


class DailyWorkflowRunner:
    """Deep workflow seam with replaceable evidence and transport adapters."""

    def __init__(
        self,
        evidence_store: EvidenceStore,
        signal_ledger: SignalLedger,
        promotion_policy: PromotionPolicy,
        outbox: SQLiteOutbox,
        *,
        repository: AgenticRepository | None = None,
        research_pipeline: ResearchPipeline | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.signal_ledger = signal_ledger
        self.promotion_policy = promotion_policy
        self.outbox = outbox
        self.repository = repository
        self.research_pipeline = research_pipeline or (
            ResearchPipeline(repository) if repository is not None else None
        )
        # Agentic repositories are workspace-specific, but the shared event
        # outbox is not.  Namespace only the shared-outbox key so equal daily
        # run keys from two workspaces cannot alias one another.  Keep the
        # legacy default key for existing anonymous/test consumers.
        clean_workspace = str(workspace_id or "").strip()
        self.workspace_id = "" if clean_workspace in {"", "default"} else clean_workspace

    def _event_idempotency_key(self, run_key: str) -> str:
        prefix = f"{self.workspace_id}:" if self.workspace_id else ""
        return f"{prefix}daily-brief:{run_key}"

    def run(
        self,
        *,
        watchlist: Sequence[str],
        source: EvidenceSource,
        evidence_items: Sequence[EvidenceItem],
        candidates: Sequence[SignalCandidate] = (),
        query: str = "watchlist_daily_brief",
        captured_at: Optional[str] = None,
        contexts: Mapping[str, ResearchContext | Mapping[str, Any]] | None = None,
        run_key: str | None = None,
        snapshot_metadata: Mapping[str, Any] | None = None,
    ) -> DailyBrief:
        timestamp = captured_at or utc_now()
        symbols = tuple(dict.fromkeys(watchlist))
        normalized_run_key = str(run_key or "").strip() or f"daily:{timestamp[:10]}:{','.join(symbols)}"
        existing = self._existing_brief(normalized_run_key)
        if existing is not None:
            return existing
        self.evidence_store.save_source(source)
        snapshot = EvidenceSnapshot(
            id=uuid.uuid4().hex,
            captured_at=timestamp,
            query=query,
            metadata={
                "watchlist": list(symbols),
                "run_key": normalized_run_key,
                "collection_status": "ok" if evidence_items else "empty",
                "evidence_status": "citable" if evidence_items else "not_citable",
                **dict(snapshot_metadata or {}),
            },
        )
        self.evidence_store.save_snapshot(snapshot)
        stored_items: List[EvidenceItem] = []
        for item in evidence_items:
            stored = self.evidence_store.save_item(item)
            stored_items.append(stored)
            self.evidence_store.link(
                EvidenceLink(snapshot_id=snapshot.id, item_id=stored.id, symbol=stored.symbol)
            )
        snapshot = self.evidence_store.seal(snapshot.id)

        research_jobs: List[str] = []
        if self.research_pipeline is not None:
            for symbol in symbols:
                supplied = (contexts or {}).get(symbol) or (contexts or {}).get(symbol[-6:]) or {}
                research_context = self._context_for_symbol(
                    symbol,
                    supplied,
                    snapshot_id=snapshot.id,
                    captured_at=timestamp,
                    evidence_count=sum(1 for item in stored_items if item.symbol in {None, symbol, symbol[-6:]}),
                )
                job = self.research_pipeline.run(
                    symbol,
                    research_context,
                    run_key=f"{normalized_run_key}:research:{symbol[-6:]}",
                )
                research_jobs.append(job.id)
                if job.decision_signal_id:
                    self.signal_ledger.record_provenance(
                        job.decision_signal_id,
                        source_type="research_context",
                        source_id=job.id,
                        evidence_snapshot_id=snapshot.id,
                        details={"stock_code": job.code, "run_key": job.run_key or normalized_run_key},
                        recorded_at=timestamp,
                    )

        promotion_results: List[PromotionResult] = []
        for candidate in candidates:
            evidence_count = sum(
                1 for item in stored_items if item.symbol in {None, candidate.symbol}
            )
            context = candidate.context
            if evidence_count > context.evidence_count:
                context = replace(context, evidence_count=evidence_count)
            decision = self.promotion_policy.evaluate(context, target=candidate.target)
            provenance = self.signal_ledger.record_provenance(
                candidate.signal_id,
                source_type="evidence_snapshot",
                source_id=snapshot.id,
                evidence_snapshot_id=snapshot.id,
                details={"symbol": candidate.symbol, "policy_version": decision.policy_version},
                recorded_at=timestamp,
            )
            ledger_event_id: Optional[str] = None
            if decision.approved:
                event = self.signal_ledger.append_transition(
                    candidate.signal_id,
                    candidate.from_status,
                    decision.target,
                    actor="daily_workflow",
                    reason="promotion policy approved",
                    evidence_snapshot_id=snapshot.id,
                    metadata={"provenance_id": provenance.provenance_id, "policy_version": decision.policy_version},
                    occurred_at=timestamp,
                )
                ledger_event_id = event.event_id
            promotion_results.append(
                PromotionResult(signal_id=candidate.signal_id, decision=decision, ledger_event_id=ledger_event_id)
            )

        payload = {
            "snapshot_id": snapshot.id,
            "watchlist": list(symbols),
            "evidence_count": len(stored_items),
            "research_jobs": research_jobs,
            "run_key": normalized_run_key,
            "promotions": [
                {
                    "signal_id": result.signal_id,
                    "target": result.decision.target,
                    "approved": result.decision.approved,
                    "failed_gates": list(result.decision.failed_gates),
                }
                for result in promotion_results
            ],
        }
        event = DomainEvent.create(
            "daily.brief.ready",
            snapshot.id,
            payload,
            idempotency_key=self._event_idempotency_key(normalized_run_key),
            occurred_at=timestamp,
        )
        event_id = self.outbox.publish(event)
        brief = DailyBrief(
            snapshot_id=snapshot.id,
            captured_at=timestamp,
            watchlist=symbols,
            evidence_count=len(stored_items),
            promotions=tuple(promotion_results),
            event_id=event_id,
            research_jobs=tuple(research_jobs),
            report_count=len(research_jobs),
            markdown=self._render_markdown(symbols, snapshot, research_jobs, stored_items, timestamp),
            run_key=normalized_run_key,
        )
        if self.repository is not None:
            self.repository.save_daily_brief(brief)
        return brief

    def _existing_brief(self, run_key: str) -> DailyBrief | None:
        if self.repository is None:
            return None
        persisted = self.repository.get_daily_brief(run_key)
        if persisted is not None:
            snapshot_id = str(persisted.get("snapshot_id") or "")
            snapshot = self.evidence_store.get_snapshot(snapshot_id) if snapshot_id else None
            if snapshot is not None:
                brief = DailyBrief(
                    snapshot_id=snapshot.id,
                    captured_at=str(persisted.get("captured_at") or snapshot.captured_at),
                    watchlist=tuple(persisted.get("watchlist") or ()),
                    evidence_count=int(persisted.get("evidence_count") or 0),
                    promotions=(),
                    event_id=str(persisted.get("event_id") or ""),
                    research_jobs=tuple(persisted.get("research_jobs") or ()),
                    report_count=int(persisted.get("report_count") or 0),
                    markdown=str(persisted.get("markdown") or ""),
                    run_key=run_key,
                )
                return self._ensure_recovered_event(brief, self.evidence_store.list_items(snapshot.id))
        jobs = self.repository.list_research_jobs(limit=500)
        matching = [job for job in jobs if job.run_key and job.run_key.startswith(run_key + ":research:")]
        if not matching:
            return None
        snapshot_id = str((matching[0].context or {}).get("evidence_snapshot_id") or "")
        snapshot = self.evidence_store.get_snapshot(snapshot_id) if snapshot_id else None
        if snapshot is None:
            return None
        event_id = self._find_event_id(run_key)
        brief = DailyBrief(
            snapshot_id=snapshot.id,
            captured_at=snapshot.captured_at,
            watchlist=tuple(snapshot.metadata.get("watchlist") or ()),
            evidence_count=len(self.evidence_store.list_items(snapshot.id)),
            promotions=(),
            event_id=event_id,
            research_jobs=tuple(job.id for job in sorted(matching, key=lambda item: item.id)),
            report_count=len(matching),
            markdown=self._render_markdown(tuple(snapshot.metadata.get("watchlist") or ()), snapshot, [job.id for job in matching], self.evidence_store.list_items(snapshot.id), snapshot.captured_at),
            run_key=run_key,
        )
        return self._ensure_recovered_event(brief, self.evidence_store.list_items(snapshot.id))

    def _ensure_recovered_event(self, brief: DailyBrief, items: Sequence[EvidenceItem]) -> DailyBrief:
        """Repair the last two durable projections after a partial retry.

        Evidence, Agentic SQLite, and the event outbox are separate stores, so
        a process crash can leave research rows without the final brief or
        event. The same run key makes this repair idempotent on retry.
        """

        event_id = brief.event_id or self._find_event_id(brief.run_key)
        event_exists = False
        if event_id:
            try:
                event_exists = self.outbox.get(event_id) is not None
            except Exception:
                event_exists = False
        if not event_exists:
            event = DomainEvent.create(
                "daily.brief.ready",
                brief.snapshot_id,
                {
                    "snapshot_id": brief.snapshot_id,
                    "watchlist": list(brief.watchlist),
                    "evidence_count": brief.evidence_count,
                    "research_jobs": list(brief.research_jobs),
                    "run_key": brief.run_key,
                },
                idempotency_key=self._event_idempotency_key(brief.run_key),
                occurred_at=brief.captured_at,
            )
            event_id = self.outbox.publish(event)
        recovered = replace(brief, event_id=event_id)
        if self.repository is not None:
            persisted = self.repository.get_daily_brief(brief.run_key)
            if persisted is None or str(persisted.get("event_id") or "") != event_id:
                self.repository.save_daily_brief(recovered)
        return recovered

    def _find_event_id(self, run_key: str) -> str:
        connection = getattr(self.outbox, "connection", None)
        if connection is None:
            return ""
        try:
            row = connection.execute(
                "SELECT event_id FROM outbox_events WHERE idempotency_key = ? LIMIT 1",
                (self._event_idempotency_key(run_key),),
            ).fetchone()
        except Exception:
            return ""
        return "" if row is None else str(row[0])

    @staticmethod
    def _context_for_symbol(
        symbol: str,
        supplied: ResearchContext | Mapping[str, Any],
        *,
        snapshot_id: str,
        captured_at: str,
        evidence_count: int,
    ) -> ResearchContext:
        if isinstance(supplied, ResearchContext):
            if supplied.evidence_snapshot_id == snapshot_id:
                return supplied
            payload = supplied.to_dict()
        else:
            payload = dict(supplied or {})
        payload.setdefault("as_of", captured_at)
        payload.setdefault("evidence_snapshot_id", snapshot_id)
        payload.setdefault("evidence_status", "citable" if evidence_count else "not_citable")
        payload.setdefault("data_quality", "partial" if not evidence_count else "complete")
        payload.setdefault("evidence_window", {"captured_at": captured_at, "count": evidence_count})
        return ResearchContext.from_mapping(symbol, payload, as_of=captured_at, evidence_snapshot_id=snapshot_id)

    @staticmethod
    def _render_markdown(
        symbols: Sequence[str],
        snapshot: EvidenceSnapshot,
        research_jobs: Sequence[str],
        items: Sequence[EvidenceItem],
        captured_at: str,
    ) -> str:
        lines = [
            f"# 每日投研简报 · {captured_at[:10]}",
            "",
            f"- 观察范围：{', '.join(symbols) or '未配置'}",
            f"- 证据快照：`{snapshot.id}`（{'可引用' if snapshot.citable else '不可引用/为空'}）",
            f"- 证据条数：{len(items)}",
            "",
            "## 研究任务",
        ]
        if research_jobs:
            lines.extend(f"- `{job_id}`" for job_id in research_jobs)
        else:
            lines.append("- 暂无研究任务")
        lines.extend(["", "## 证据摘要"])
        lines.extend(f"- {item.title or item.content[:80]}（{item.observed_at}）" for item in items[:20])
        if not items:
            lines.append("- 本次没有可引用证据，研究结论必须标记为降级或观察状态。")
        return "\n".join(lines)
