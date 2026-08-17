"""Evidence storage seam for reproducible research and signal provenance."""

from .models import EvidenceItem, EvidenceLink, EvidenceQuery, EvidenceSnapshot, EvidenceSource
from .collector import EvidenceIngestResult, ingest_records
from .store import EvidenceStore, InMemoryEvidenceStore, SQLiteEvidenceStore

__all__ = [
    "EvidenceItem",
    "EvidenceIngestResult",
    "EvidenceLink",
    "EvidenceQuery",
    "EvidenceSnapshot",
    "EvidenceSource",
    "EvidenceStore",
    "InMemoryEvidenceStore",
    "SQLiteEvidenceStore",
    "ingest_records",
]
