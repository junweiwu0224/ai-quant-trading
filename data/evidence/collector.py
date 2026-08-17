"""Adapters that turn external collector records into citable evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from .models import EvidenceItem, EvidenceLink, EvidenceSnapshot, EvidenceSource, utc_now
from .store import EvidenceStore


@dataclass(frozen=True)
class EvidenceIngestResult:
    snapshot: EvidenceSnapshot
    items: tuple[EvidenceItem, ...]


def _fingerprint(record: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ingest_records(
    store: EvidenceStore,
    *,
    source: EvidenceSource,
    records: Iterable[Mapping[str, Any]],
    query: str,
    captured_at: Optional[str] = None,
    symbol_key: str = "symbol",
    title_key: str = "title",
    content_key: str = "content",
    observed_at_key: str = "observed_at",
    url_key: str = "url",
    snapshot_metadata: Optional[Mapping[str, Any]] = None,
    raw_payload: Any = None,
    raw_payload_key: Optional[str] = None,
) -> EvidenceIngestResult:
    """Persist one collector run and return its exact snapshot."""

    timestamp = captured_at or utc_now()
    materialized_records = [dict(record) for record in records]
    metadata = {"source_id": source.id, **dict(snapshot_metadata or {})}
    collection_status = str(metadata.get("collection_status") or "").strip().lower()
    if not collection_status:
        collection_status = "ok" if materialized_records else "empty"
        metadata["collection_status"] = collection_status
    metadata.setdefault(
        "snapshot_kind",
        "collection_run",
    )
    metadata.setdefault(
        "collection_request",
        {"query": query, "captured_at": timestamp},
    )
    metadata.setdefault(
        "evidence_status",
        "citable"
        if materialized_records and collection_status not in {"failed", "empty"}
        else "not_citable",
    )
    store.save_source(source)
    snapshot = EvidenceSnapshot(
        id="snapshot_%s" % uuid.uuid4().hex[:16],
        captured_at=timestamp,
        query=query,
        metadata=metadata,
    )
    store.save_snapshot(snapshot)
    items: list[EvidenceItem] = []
    for data in materialized_records:
        normalized_metadata = dict(data)
        record_raw_payload = raw_payload
        if raw_payload_key:
            record_raw_payload = normalized_metadata.pop(raw_payload_key, raw_payload)
        item = EvidenceItem(
            id="evidence_%s" % uuid.uuid4().hex[:16],
            source_id=source.id,
            title=str(data.get(title_key) or data.get("headline") or ""),
            content=str(data.get(content_key) or data.get("summary") or data.get("text") or ""),
            observed_at=str(data.get(observed_at_key) or timestamp),
            url=None if data.get(url_key) is None else str(data.get(url_key)),
            symbol=None if data.get(symbol_key) is None else str(data.get(symbol_key)),
            fingerprint=_fingerprint(data),
            raw_payload=record_raw_payload,
            metadata=normalized_metadata,
        )
        stored = store.save_item(item)
        store.link(EvidenceLink(snapshot_id=snapshot.id, item_id=stored.id, symbol=stored.symbol))
        symbols = data.get("symbols")
        link_symbol = getattr(store, "link_symbol", None)
        if isinstance(symbols, (list, tuple, set)):
            for symbol in symbols:
                normalized_symbol = str(symbol)
                if callable(link_symbol):
                    link_symbol(snapshot.id, stored.id, normalized_symbol)
                else:
                    # Compatibility path for older Adapters. A distinct
                    # relation preserves multiple symbols without requiring
                    # the newer auxiliary-table method.
                    store.link(
                        EvidenceLink(
                            snapshot_id=snapshot.id,
                            item_id=stored.id,
                            relation="symbol:%s" % normalized_symbol,
                            symbol=normalized_symbol,
                        )
                    )
        elif stored.symbol:
            if callable(link_symbol):
                link_symbol(snapshot.id, stored.id, stored.symbol)
            else:
                store.link(
                    EvidenceLink(
                        snapshot_id=snapshot.id,
                        item_id=stored.id,
                        relation="symbol:%s" % stored.symbol,
                        symbol=stored.symbol,
                    )
                )
        items.append(stored)
    snapshot = store.seal(snapshot.id)
    return EvidenceIngestResult(
        snapshot=snapshot,
        items=tuple(items),
    )
