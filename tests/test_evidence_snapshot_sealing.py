import sqlite3

import pytest

from data.evidence.models import EvidenceItem, EvidenceLink, EvidenceSnapshot
from data.evidence.store import InMemoryEvidenceStore, SQLiteEvidenceStore


@pytest.mark.parametrize("factory", [InMemoryEvidenceStore, lambda: SQLiteEvidenceStore(sqlite3.connect(":memory:"))])
def test_sealed_snapshot_rejects_late_links(factory):
    store = factory()
    store.save_item(EvidenceItem("item", "source", "Title", "Fact", "2026-08-12T00:00:00Z"))
    store.save_snapshot(EvidenceSnapshot("snap", "2026-08-12T00:00:01Z", "fixture"))
    store.link(EvidenceLink("snap", "item"))
    sealed = store.seal("snap")
    assert sealed.sealed
    with pytest.raises(ValueError):
        store.link(EvidenceLink("snap", "item", relation="late"))


def test_readonly_sqlite_evidence_store_does_not_initialize_or_write(tmp_path):
    path = tmp_path / "evidence.db"
    writable = SQLiteEvidenceStore(path)
    writable.save_snapshot(EvidenceSnapshot("snap", "2026-08-12T00:00:01Z", "fixture"))
    writable.close()
    readonly = SQLiteEvidenceStore(path, readonly=True)
    assert readonly.get_snapshot("snap") is not None
    with pytest.raises(sqlite3.OperationalError):
        readonly.save_snapshot(EvidenceSnapshot("other", "2026-08-12T00:00:01Z", "fixture"))
    readonly.close()
