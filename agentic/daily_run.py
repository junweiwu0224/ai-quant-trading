"""Orchestrate one auditable daily research run.

This module is the application seam between external intelligence collectors
and the existing evidence-bound ``DailyWorkflowRunner``. It owns collection
ordering, context construction, run-key replay, and operation reporting; it
does not introduce a second database or a second backtest lifecycle.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from agentic.daily_workflow import DailyBrief, DailyWorkflowRunner
from agentic.models import ResearchContext
from agentic.operations import OperationConflict, OperationRecord, normalize_operation_id
from agentic.repository import AgenticRepository
from agentic.research_pipeline import ResearchPipeline
from agentic.signals import SignalService
from data.evidence.models import EvidenceItem, EvidenceSource, utc_now
from agentic.promotion import PromotionPolicy
from data.evidence.store import EvidenceStore
from engine.events.outbox import SQLiteOutbox


MarketCollector = Callable[..., Awaitable[Mapping[str, Any]] | Mapping[str, Any]]
StockCollector = Callable[..., Awaitable[Mapping[str, Any]] | Mapping[str, Any]]


@dataclass(frozen=True)
class DailyRunResult:
    brief: DailyBrief
    operation: OperationRecord | None
    collection: Mapping[str, Any]


class DailyResearchRunService:
    """Run collection, research, brief persistence, and outbox publication."""

    def __init__(
        self,
        evidence_store: EvidenceStore,
        repository: AgenticRepository,
        outbox: SQLiteOutbox,
        *,
        signal_service: SignalService | None = None,
        research_pipeline: ResearchPipeline | None = None,
        market_collector: MarketCollector | None = None,
        stock_collector: StockCollector | None = None,
        market_source: EvidenceSource | None = None,
        owner: str = "daily-research",
        workspace_id: str | None = None,
    ) -> None:
        self.evidence_store = evidence_store
        self.repository = repository
        self.outbox = outbox
        self.signal_service = signal_service or SignalService(repository)
        self.research_pipeline = research_pipeline or ResearchPipeline(
            repository, signal_service=self.signal_service
        )
        self.market_collector = market_collector or self._default_market_collector
        self.stock_collector = stock_collector or self._default_stock_collector
        self.market_source = market_source or EvidenceSource(
            id="daily-research:market-news",
            name="Daily research market intelligence",
            kind="daily_research",
            uri="agentic.daily_run",
            trust_tier="derived",
        )
        self.owner = str(owner or "daily-research")
        self.workspace_id = str(workspace_id or "").strip()

    async def run(
        self,
        *,
        watchlist: Sequence[str],
        run_key: str,
        operation_id: str | None = None,
        captured_at: str | None = None,
        max_market_items: int = 30,
        max_stock_items: int = 20,
        contexts: Mapping[str, ResearchContext | Mapping[str, Any]] | None = None,
    ) -> DailyRunResult:
        symbols = tuple(dict.fromkeys(str(code).strip() for code in watchlist if str(code).strip()))
        if not symbols:
            raise ValueError("watchlist must contain at least one A-share code")
        normalized_run_key = str(run_key or "").strip()
        if not normalized_run_key:
            raise ValueError("run_key is required")
        normalized_operation_id = normalize_operation_id(operation_id or f"daily-run:{normalized_run_key}")
        request_payload = self._request_payload(
            symbols, normalized_run_key, max_market_items, max_stock_items
        )

        existing_operation = self._existing_operation(normalized_operation_id)
        if existing_operation is not None:
            if existing_operation.command != "daily.research.run" or existing_operation.aggregate_type != "daily_brief" or existing_operation.aggregate_id != normalized_run_key or dict(existing_operation.request) != request_payload:
                raise OperationConflict("operation_id was already used for different daily run facts")
            if existing_operation.status != "completed":
                raise ValueError("daily run operation is not completed: %s" % normalized_operation_id)
            brief = self.repository.get_daily_brief(normalized_run_key)
            if brief is None:
                raise RuntimeError("completed daily run has no brief: %s" % normalized_run_key)
            return DailyRunResult(
                brief=self._brief_from_row(brief),
                operation=existing_operation,
                collection={"status": "replayed", "run_key": normalized_run_key},
            )

        existing_brief = self.repository.get_daily_brief(normalized_run_key)
        if existing_brief is not None:
            operation = self.repository.record_operation(
                normalized_operation_id,
                command="daily.research.run",
                aggregate_type="daily_brief",
                aggregate_id=normalized_run_key,
                request=request_payload,
                status="completed",
                result={"run_key": normalized_run_key, "event_id": existing_brief.get("event_id", ""), "replayed": True},
            )
            return DailyRunResult(
                brief=self._brief_from_row(existing_brief),
                operation=operation,
                collection={"status": "replayed", "run_key": normalized_run_key},
            )

        timestamp = captured_at or utc_now()
        market = await self._call_market_collector(
            max_items=max(1, int(max_market_items)),
            collection_key=f"{normalized_run_key}:market",
        )
        stock_results: list[Mapping[str, Any]] = []
        # EvidenceStore adapters are deliberately written sequentially. This
        # keeps one SQLite connection out of concurrent collector writes while
        # still allowing each adapter to manage its own provider I/O.
        for symbol in symbols:
            stock_results.append(
                await self._call_stock_collector(
                    symbol,
                    max_items=max(1, int(max_stock_items)),
                    collection_key=f"{normalized_run_key}:stock:{symbol[-6:]}",
                )
            )

        evidence_items: list[EvidenceItem] = []
        source_snapshot_ids: list[str] = []
        collection_statuses: list[str] = []
        self._append_collected_items(market, evidence_items, source_snapshot_ids, collection_statuses)
        for result in stock_results:
            self._append_collected_items(result, evidence_items, source_snapshot_ids, collection_statuses)

        source_health = self._source_health(market, stock_results)
        daily_source = EvidenceSource(
            id=self.market_source.id,
            name=self.market_source.name,
            kind=self.market_source.kind,
            uri=self.market_source.uri,
            trust_tier=self.market_source.trust_tier,
            metadata={**dict(self.market_source.metadata), "run_key": normalized_run_key},
        )
        runner = DailyWorkflowRunner(
            self.evidence_store,
            self.signal_service.ledger,
            # A daily run creates research signals; it does not promote them.
            # Existing promotion candidates remain an explicit caller concern.
            promotion_policy=PromotionPolicy(),
            outbox=self.outbox,
            repository=self.repository,
            research_pipeline=self.research_pipeline,
            workspace_id=self.workspace_id,
        )
        prepared_contexts = self._prepare_contexts(
            symbols,
            contexts or {},
            timestamp=timestamp,
            market=market,
            stock_results=stock_results,
            source_health=source_health,
        )
        brief = runner.run(
            watchlist=symbols,
            source=daily_source,
            evidence_items=evidence_items,
            query="daily_research_run",
            captured_at=timestamp,
            contexts=prepared_contexts,
            run_key=normalized_run_key,
            snapshot_metadata={
                "collection_status": self._aggregate_status(collection_statuses),
                "evidence_status": "citable" if evidence_items else "not_citable",
                "source_health": source_health,
                "source_snapshot_ids": source_snapshot_ids,
                "market_collection": self._collection_summary(market),
                "stock_collections": [self._collection_summary(item) for item in stock_results],
            },
        )
        operation = self.repository.record_operation(
            normalized_operation_id,
            command="daily.research.run",
            aggregate_type="daily_brief",
            aggregate_id=normalized_run_key,
            request=request_payload,
            status="completed",
            result={
                "run_key": normalized_run_key,
                "snapshot_id": brief.snapshot_id,
                "event_id": brief.event_id,
                "research_jobs": list(brief.research_jobs),
                "replayed": False,
            },
        )
        return DailyRunResult(
            brief=brief,
            operation=operation,
            collection={
                "status": self._aggregate_status(collection_statuses),
                "run_key": normalized_run_key,
                "source_snapshot_ids": source_snapshot_ids,
                "source_health": source_health,
            },
        )

    async def _call_market_collector(self, *, max_items: int, collection_key: str) -> Mapping[str, Any]:
        try:
            return await self._resolve(self.market_collector, self.evidence_store, max_items, self.market_source, collection_key=collection_key, owner=self.owner)
        except Exception as exc:
            return {"collection_status": "failed", "errors": [str(exc)], "news": [], "evidence_count": 0}

    async def _call_stock_collector(self, symbol: str, *, max_items: int, collection_key: str) -> Mapping[str, Any]:
        try:
            return await self._resolve(self.stock_collector, symbol, self.evidence_store, max_items, collection_key=collection_key, owner=self.owner)
        except Exception as exc:
            return {"code": symbol, "collection_status": "failed", "errors": [str(exc)], "news": [], "evidence_count": 0}

    @staticmethod
    async def _resolve(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        value = function(*args, **kwargs)
        if inspect.isawaitable(value):
            value = await value
        if not isinstance(value, Mapping):
            raise TypeError("daily collector must return a mapping")
        return value

    @staticmethod
    async def _default_market_collector(store: EvidenceStore, max_items: int, source: EvidenceSource, **kwargs: Any) -> Mapping[str, Any]:
        from alpha.news_collector import collect_market_news_evidence

        return await collect_market_news_evidence(store, max_items=max_items, source=source, **kwargs)

    @staticmethod
    async def _default_stock_collector(symbol: str, store: EvidenceStore, max_items: int, **kwargs: Any) -> Mapping[str, Any]:
        from alpha.news_collector import collect_stock_news_evidence

        return await collect_stock_news_evidence(symbol, store, max_items=max_items, **kwargs)

    def _existing_operation(self, operation_id: str) -> OperationRecord | None:
        try:
            return self.repository.get_operation(operation_id)
        except KeyError:
            return None

    def _append_collected_items(self, result: Mapping[str, Any], target: list[EvidenceItem], snapshot_ids: list[str], statuses: list[str]) -> None:
        snapshot_id = str(result.get("evidence_snapshot_id") or result.get("collection_snapshot_id") or "").strip()
        if snapshot_id:
            snapshot_ids.append(snapshot_id)
        status = str(result.get("collection_status") or ("ok" if result.get("evidence_count") else "empty"))
        statuses.append(status)
        # A collector may be a lightweight test adapter that returns items
        # directly; canonical collectors return a snapshot id which is read
        # back from the same EvidenceStore.
        if snapshot_id:
            try:
                target.extend(self.evidence_store.list_items(snapshot_id))
            except (KeyError, ValueError):
                pass

    def _prepare_contexts(self, symbols: Sequence[str], supplied: Mapping[str, Any], *, timestamp: str, market: Mapping[str, Any], stock_results: Sequence[Mapping[str, Any]], source_health: Mapping[str, Any]) -> dict[str, ResearchContext | Mapping[str, Any]]:
        market_rows = self._local_market_rows(symbols)
        result_by_code = {str(item.get("code") or "").strip(): item for item in stock_results}
        prepared: dict[str, ResearchContext | Mapping[str, Any]] = {}
        for symbol in symbols:
            plain = symbol[-6:]
            stock_result = result_by_code.get(symbol) or result_by_code.get(plain) or {}
            news = stock_result.get("news") if isinstance(stock_result.get("news"), list) else []
            row = market_rows.get(plain, {})
            base = dict(supplied.get(symbol) or supplied.get(plain) or {})
            base.setdefault("as_of", timestamp)
            base.setdefault("market_data", self._json_safe(row))
            base.setdefault("technicals", self._technical_summary(row))
            base.setdefault("sentiment", {"news_count": len(news), "overall": market.get("overall_sentiment", 0)})
            base.setdefault("themes", {"keywords": stock_result.get("hot_keywords") or []})
            base.setdefault("source_health", {**dict(source_health), "stock_news": "ok" if news else "empty"})
            base.setdefault("data_quality", "complete" if row else "partial")
            prepared[plain] = base
        return prepared

    @staticmethod
    def _local_market_rows(symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
        try:
            from data.storage import DataStorage

            rows = DataStorage().get_latest_market_rows_for_codes(list(symbols))
            return {str(row.get("code") or "").strip(): dict(row) for row in rows}
        except Exception:
            return {}

    @staticmethod
    def _technical_summary(row: Mapping[str, Any]) -> dict[str, Any]:
        close = _number(row.get("close"))
        previous = _number(row.get("prev_close"))
        return {
            "close": close,
            "change_pct": None if close is None or previous in (None, 0) else round((close / previous - 1) * 100, 4),
            "high": _number(row.get("high")),
            "low": _number(row.get("low")),
            "volume": _number(row.get("volume")),
            "amount": _number(row.get("amount")),
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): DailyResearchRunService._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [DailyResearchRunService._json_safe(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)

    @staticmethod
    def _source_health(market: Mapping[str, Any], stocks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        statuses = [str(market.get("collection_status") or "unknown")] + [str(item.get("collection_status") or "unknown") for item in stocks]
        return {
            "market_news": statuses[0],
            "stock_news": "ok" if any(status == "ok" for status in statuses[1:]) else ("empty" if stocks else "unknown"),
            "partial": any(status in {"partial", "failed", "in_progress"} for status in statuses),
        }

    @staticmethod
    def _collection_summary(result: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": result.get("collection_status") or "unknown",
            "snapshot_id": result.get("evidence_snapshot_id") or result.get("collection_snapshot_id"),
            "count": result.get("evidence_count", 0),
            "errors": result.get("partial_errors") or result.get("errors") or [],
        }

    @staticmethod
    def _aggregate_status(statuses: Sequence[str]) -> str:
        normalized = {str(item).lower() for item in statuses}
        if not statuses or normalized <= {"empty"}:
            return "empty"
        if "ok" in normalized and normalized - {"ok", "empty", "reused"}:
            return "partial"
        if normalized <= {"reused", "ok"}:
            return "ok"
        if "ok" in normalized or "reused" in normalized:
            return "partial"
        return "failed"

    @staticmethod
    def _request_payload(symbols: Sequence[str], run_key: str, max_market_items: int, max_stock_items: int) -> dict[str, Any]:
        return {"watchlist": list(symbols), "run_key": run_key, "max_market_items": int(max_market_items), "max_stock_items": int(max_stock_items)}

    @staticmethod
    def _brief_from_row(row: Mapping[str, Any]) -> DailyBrief:
        return DailyBrief(
            snapshot_id=str(row.get("snapshot_id") or ""),
            captured_at=str(row.get("captured_at") or ""),
            watchlist=tuple(row.get("watchlist") or ()),
            evidence_count=int(row.get("evidence_count") or 0),
            promotions=(),
            event_id=str(row.get("event_id") or ""),
            research_jobs=tuple(row.get("research_jobs") or ()),
            report_count=int(row.get("report_count") or 0),
            markdown=str(row.get("markdown") or ""),
            run_key=str(row.get("run_key") or ""),
        )


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None
