"""Immutable records shared by evidence-store adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class EvidenceSource:
    id: str
    name: str
    kind: str = "unknown"
    uri: Optional[str] = None
    trust_tier: str = "unverified"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    source_id: str
    title: str
    content: str
    observed_at: str
    url: Optional[str] = None
    symbol: Optional[str] = None
    fingerprint: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceSnapshot:
    id: str
    captured_at: str
    query: str
    record_ids: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    sealed: bool = False

    @property
    def citable(self) -> bool:
        """Whether this sealed collection run contains citeable evidence.

        Older snapshots without an explicit status remain citeable when
        sealed. New collector runs set ``evidence_status`` so failed/empty
        runs can be audited without being mistaken for supporting evidence.
        """

        if not self.sealed:
            return False
        status = str(self.metadata.get("evidence_status") or "").strip().lower()
        if status:
            return status == "citable"
        collection_status = str(self.metadata.get("collection_status") or "").strip().lower()
        return collection_status not in {"failed", "empty"}


@dataclass(frozen=True)
class EvidenceLink:
    snapshot_id: str
    item_id: str
    relation: str = "observed"
    symbol: Optional[str] = None


@dataclass(frozen=True)
class EvidenceQuery:
    symbol: Optional[str] = None
    source_id: Optional[str] = None
    observed_after: Optional[str] = None
    text: Optional[str] = None
    limit: int = 100
