from data.evidence.collector import ingest_records
from data.evidence.models import EvidenceSnapshot, EvidenceSource
from data.evidence.store import InMemoryEvidenceStore

def test_ingest_records_returns_a_citable_snapshot():
    store = InMemoryEvidenceStore()
    result = ingest_records(
        store,
        source=EvidenceSource(id="fixture", name="Fixture", kind="test", trust_tier="test"),
        records=[
            {
                "title": "Headline",
                "content": "Observed fact",
                "observed_at": "2026-08-12T08:00:00Z",
                "symbol": "600000",
                "url": "https://example.test/item",
            }
        ],
        query="fixture-news",
        captured_at="2026-08-12T08:01:00Z",
    )
    assert result.snapshot.record_ids == (result.items[0].id,)
    assert store.list_sources()[0].id == "fixture"
    assert store.list_items(result.snapshot.id)[0].url == "https://example.test/item"

def test_ingest_records_preserves_multiple_symbols_and_snapshot_metadata():
    store = InMemoryEvidenceStore()
    result = ingest_records(
        store,
        source=EvidenceSource(id="fixture", name="Fixture"),
        records=[
            {
                "title": "Shared event",
                "content": "Observed fact",
                "symbol": "600000",
                "symbols": ["600000", "000001"],
            }
        ],
        query="multi-symbol",
        snapshot_metadata={"collection_status": "partial", "source_errors": ["secondary_down"]},
    )
    item_id = result.items[0].id
    assert store.list_item_symbols(result.snapshot.id, item_id) == ["000001", "600000"]
    assert result.snapshot.metadata["collection_status"] == "partial"

def test_empty_collection_is_auditable_but_not_citable():
    store = InMemoryEvidenceStore()
    result = ingest_records(
        store,
        source=EvidenceSource("fixture-empty", "Fixture"),
        records=[],
        query="empty",
        snapshot_metadata={"collection_status": "empty"},
    )

    assert result.snapshot.sealed
    assert result.snapshot.metadata["snapshot_kind"] == "collection_run"
    assert result.snapshot.metadata["evidence_status"] == "not_citable"
    assert not result.snapshot.citable

def test_ingest_records_supports_legacy_adapter_without_link_symbol():
    class LegacyEvidenceStore:
        def __init__(self):
            self.sources = {}
            self.items = {}
            self.snapshots = {}
            self.links = []

        def save_source(self, source):
            self.sources[source.id] = source
            return source

        def save_item(self, item):
            self.items[item.id] = item
            return item

        def save_snapshot(self, snapshot):
            self.snapshots[snapshot.id] = snapshot
            return snapshot

        def link(self, link):
            self.links.append(link)
            return link

        def seal(self, snapshot_id):
            snapshot = self.snapshots[snapshot_id]
            self.snapshots[snapshot_id] = EvidenceSnapshot(
                snapshot.id,
                snapshot.captured_at,
                snapshot.query,
                snapshot.record_ids,
                snapshot.metadata,
                True,
            )
            return self.snapshots[snapshot_id]

    store = LegacyEvidenceStore()
    result = ingest_records(
        store,
        source=EvidenceSource("legacy", "Legacy"),
        records=[{"title": "fact", "content": "body", "symbols": ["000001", "600000"]}],
        query="legacy",
    )

    symbol_links = [link for link in store.links if link.symbol]
    assert {link.symbol for link in symbol_links} == {"000001", "600000"}
    assert result.snapshot.citable
