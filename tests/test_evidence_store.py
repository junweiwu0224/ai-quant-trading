import sqlite3

import pytest

from data.evidence.models import EvidenceItem, EvidenceLink, EvidenceQuery, EvidenceSnapshot, EvidenceSource
from data.evidence.store import InMemoryEvidenceStore, SQLiteEvidenceStore


@pytest.mark.parametrize("factory", [InMemoryEvidenceStore, lambda: SQLiteEvidenceStore(":memory:")])
def test_evidence_snapshot_is_reproducible(factory):
    store = factory()
    source = EvidenceSource(id="news", name="Test News", kind="fixture", trust_tier="test")
    item = EvidenceItem(
        id="item-1",
        source_id=source.id,
        title="Earnings",
        content="Revenue increased",
        observed_at="2026-08-12T08:00:00Z",
        symbol="600000.SH",
        fingerprint="sha:item-1",
    )
    store.save_source(source)
    store.save_item(item)
    store.save_snapshot(EvidenceSnapshot(id="snap-1", captured_at="2026-08-12T08:01:00Z", query="daily"))
    store.link(EvidenceLink(snapshot_id="snap-1", item_id=item.id, symbol=item.symbol))

    snapshot = store.get_snapshot("snap-1")
    assert snapshot is not None
    assert snapshot.record_ids == (item.id,)
    assert store.list_items("snap-1")[0].content == "Revenue increased"
    assert store.query(EvidenceQuery(symbol="600000.SH"))[0].id == item.id


def test_sqlite_store_deduplicates_fingerprints():
    store = SQLiteEvidenceStore(sqlite3.connect(":memory:"))
    first = EvidenceItem("a", "source", "Title", "Body", "2026-08-12T00:00:00Z", fingerprint="same")
    second = EvidenceItem("b", "source", "Other", "Other", "2026-08-12T00:00:01Z", fingerprint="same")
    assert store.save_item(first).id == "a"
    assert store.save_item(second).id == "a"


def test_list_items_does_not_duplicate_item_for_multiple_relations():
    store = InMemoryEvidenceStore()
    store.save_item(EvidenceItem("item", "source", "Title", "Body", "2026-08-12T00:00:00Z"))
    store.save_snapshot(EvidenceSnapshot("snap", "2026-08-12T00:00:01Z", "fixture"))
    store.link(EvidenceLink("snap", "item", relation="observed"))
    store.link(EvidenceLink("snap", "item", relation="related"))
    assert [item.id for item in store.list_items("snap")] == ["item"]
