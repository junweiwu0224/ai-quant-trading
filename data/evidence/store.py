"""Deep evidence-store interface with SQLite and in-memory adapters.

Callers know only how to save and cite sources, items, snapshots, and links.
The snapshot/link split keeps one observed item reusable while preserving the
exact evidence set used by each report or signal.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Union

from .models import EvidenceItem, EvidenceLink, EvidenceQuery, EvidenceSnapshot, EvidenceSource


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load(value: str) -> dict:
    loaded = json.loads(value or "{}")
    return loaded if isinstance(loaded, dict) else {}


class EvidenceStore(Protocol):
    """Interface used by workflows and reports to cite evidence."""

    def save_source(self, source: EvidenceSource) -> EvidenceSource: ...

    def save_item(self, item: EvidenceItem) -> EvidenceItem: ...

    def save_snapshot(self, snapshot: EvidenceSnapshot) -> EvidenceSnapshot: ...

    def link(self, link: EvidenceLink) -> EvidenceLink: ...

    def link_symbol(self, snapshot_id: str, item_id: str, symbol: str) -> None: ...

    def list_item_symbols(self, snapshot_id: str, item_id: str) -> List[str]: ...

    def get_snapshot(self, snapshot_id: str) -> Optional[EvidenceSnapshot]: ...

    def list_items(self, snapshot_id: str) -> List[EvidenceItem]: ...

    def query(self, query: EvidenceQuery = EvidenceQuery()) -> List[EvidenceItem]: ...

    def list_sources(self) -> List[EvidenceSource]: ...

    def seal(self, snapshot_id: str) -> EvidenceSnapshot: ...


class SQLiteEvidenceStore:
    """SQLite implementation with idempotent item writes and immutable links."""

    def __init__(self, database: Union[str, Path, sqlite3.Connection], *, readonly: bool = False) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        self.readonly = readonly
        empty_readonly = False
        if isinstance(database, sqlite3.Connection):
            self.connection = database
        elif readonly:
            path = Path(database)
            if path.exists():
                self.connection = sqlite3.connect(
                    f"file:{path}?mode=ro", uri=True, timeout=5.0
                )
            else:
                # Keep audit GETs side-effect free when evidence has not yet
                # been collected: use an empty in-memory read model instead
                # of creating data/evidence.db.
                self.connection = sqlite3.connect(":memory:", timeout=5.0)
                empty_readonly = True
        else:
            path = Path(database)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(path), timeout=5.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=5000")
        if not readonly or empty_readonly:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self._initialize()

    def _assert_writable(self) -> None:
        if self.readonly:
            raise sqlite3.OperationalError("evidence store is read-only")

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidence_sources (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                uri TEXT,
                trust_tier TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence_items (
                item_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                url TEXT,
                symbol TEXT,
                fingerprint TEXT UNIQUE,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                query_text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                sealed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS evidence_links (
                snapshot_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                symbol TEXT,
                PRIMARY KEY (snapshot_id, item_id, relation),
                FOREIGN KEY (snapshot_id) REFERENCES evidence_snapshots(snapshot_id),
                FOREIGN KEY (item_id) REFERENCES evidence_items(item_id)
            );
            CREATE TABLE IF NOT EXISTS evidence_item_symbols (
                snapshot_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                PRIMARY KEY (snapshot_id, item_id, symbol),
                FOREIGN KEY (snapshot_id) REFERENCES evidence_snapshots(snapshot_id),
                FOREIGN KEY (item_id) REFERENCES evidence_items(item_id)
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_items_symbol ON evidence_items(symbol);
            CREATE INDEX IF NOT EXISTS idx_evidence_items_observed ON evidence_items(observed_at);
            CREATE INDEX IF NOT EXISTS idx_evidence_links_snapshot ON evidence_links(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_evidence_item_symbols_symbol ON evidence_item_symbols(symbol);
            """
        )
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(evidence_snapshots)").fetchall()
        }
        if "sealed" not in columns:
            self.connection.execute(
                "ALTER TABLE evidence_snapshots ADD COLUMN sealed INTEGER NOT NULL DEFAULT 0"
            )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO evidence_item_symbols(snapshot_id, item_id, symbol)
            SELECT snapshot_id, item_id, symbol
            FROM evidence_links
            WHERE symbol IS NOT NULL AND TRIM(symbol) <> ''
            """
        )
        self.connection.commit()

    def save_source(self, source: EvidenceSource) -> EvidenceSource:
        self._assert_writable()
        self.connection.execute(
            """
            INSERT INTO evidence_sources(source_id, name, kind, uri, trust_tier, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                name=excluded.name, kind=excluded.kind, uri=excluded.uri,
                trust_tier=excluded.trust_tier, metadata_json=excluded.metadata_json
            """,
            (source.id, source.name, source.kind, source.uri, source.trust_tier, _dump(dict(source.metadata))),
        )
        self.connection.commit()
        return source

    @staticmethod
    def _item_from_row(row: sqlite3.Row) -> EvidenceItem:
        return EvidenceItem(
            id=row["item_id"],
            source_id=row["source_id"],
            title=row["title"],
            content=row["content"],
            observed_at=row["observed_at"],
            url=row["url"],
            symbol=row["symbol"],
            fingerprint=row["fingerprint"],
            metadata=_load(row["metadata_json"]),
        )

    def save_item(self, item: EvidenceItem) -> EvidenceItem:
        self._assert_writable()
        with self.connection:
            if item.fingerprint:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO evidence_items(
                        item_id, source_id, title, content, observed_at, url, symbol, fingerprint, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.source_id,
                        item.title,
                        item.content,
                        item.observed_at,
                        item.url,
                        item.symbol,
                        item.fingerprint,
                        _dump(dict(item.metadata)),
                    ),
                )
                row = self.connection.execute(
                    "SELECT * FROM evidence_items WHERE fingerprint = ?", (item.fingerprint,)
                ).fetchone()
            else:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO evidence_items(
                        item_id, source_id, title, content, observed_at, url, symbol, fingerprint, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.source_id,
                        item.title,
                        item.content,
                        item.observed_at,
                        item.url,
                        item.symbol,
                        item.fingerprint,
                        _dump(dict(item.metadata)),
                    ),
                )
                row = self.connection.execute(
                    "SELECT * FROM evidence_items WHERE item_id = ?", (item.id,)
                ).fetchone()
        if row is None:
            raise RuntimeError("evidence item was not persisted")
        return self._item_from_row(row)

    def save_snapshot(self, snapshot: EvidenceSnapshot) -> EvidenceSnapshot:
        self._assert_writable()
        self.connection.execute(
            """
            INSERT OR IGNORE INTO evidence_snapshots(snapshot_id, captured_at, query_text, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (snapshot.id, snapshot.captured_at, snapshot.query, _dump(dict(snapshot.metadata))),
        )
        self.connection.commit()
        return self.get_snapshot(snapshot.id) or snapshot

    def link(self, link: EvidenceLink) -> EvidenceLink:
        self._assert_writable()
        snapshot = self.connection.execute(
            "SELECT sealed FROM evidence_snapshots WHERE snapshot_id = ?",
            (link.snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise KeyError("evidence snapshot not found: %s" % link.snapshot_id)
        if bool(snapshot["sealed"]):
            raise ValueError("evidence snapshot is sealed: %s" % link.snapshot_id)
        self.connection.execute(
            """
            INSERT OR IGNORE INTO evidence_links(snapshot_id, item_id, relation, symbol)
            VALUES (?, ?, ?, ?)
            """,
            (link.snapshot_id, link.item_id, link.relation, link.symbol),
        )
        self.connection.commit()
        return link

    def link_symbol(self, snapshot_id: str, item_id: str, symbol: str) -> None:
        symbol = str(symbol or "").strip()
        if not symbol:
            return
        if self.readonly:
            raise sqlite3.OperationalError("evidence store is read-only")
        snapshot = self.connection.execute(
            "SELECT 1 FROM evidence_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise KeyError("evidence snapshot not found: %s" % snapshot_id)
        sealed = self.connection.execute(
            "SELECT sealed FROM evidence_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if sealed is not None and bool(sealed["sealed"]):
            raise ValueError("evidence snapshot is sealed: %s" % snapshot_id)
        self.connection.execute(
            "INSERT OR IGNORE INTO evidence_item_symbols(snapshot_id, item_id, symbol) VALUES (?, ?, ?)",
            (snapshot_id, item_id, symbol),
        )
        self.connection.commit()

    def list_item_symbols(self, snapshot_id: str, item_id: str) -> List[str]:
        try:
            rows = self.connection.execute(
                "SELECT symbol FROM evidence_item_symbols WHERE snapshot_id = ? AND item_id = ? ORDER BY symbol",
                (snapshot_id, item_id),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self.connection.execute(
                """
                SELECT symbol FROM evidence_links
                WHERE snapshot_id = ? AND item_id = ? AND symbol IS NOT NULL
                ORDER BY symbol
                """,
                (snapshot_id, item_id),
            ).fetchall()
        return [str(row["symbol"]) for row in rows]

    def get_snapshot(self, snapshot_id: str) -> Optional[EvidenceSnapshot]:
        row = self.connection.execute(
            "SELECT * FROM evidence_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        record_ids = tuple(
            link_row["item_id"]
            for link_row in self.connection.execute(
                "SELECT DISTINCT item_id FROM evidence_links WHERE snapshot_id = ? ORDER BY item_id", (snapshot_id,)
            ).fetchall()
        )
        return EvidenceSnapshot(
            id=row["snapshot_id"],
            captured_at=row["captured_at"],
            query=row["query_text"],
            record_ids=record_ids,
            metadata=_load(row["metadata_json"]),
            sealed=bool(row["sealed"]),
        )

    def seal(self, snapshot_id: str) -> EvidenceSnapshot:
        self._assert_writable()
        with self.connection:
            updated = self.connection.execute(
                "UPDATE evidence_snapshots SET sealed = 1 WHERE snapshot_id = ?",
                (snapshot_id,),
            ).rowcount
        if updated != 1:
            raise KeyError("evidence snapshot not found: %s" % snapshot_id)
        return self.get_snapshot(snapshot_id)  # type: ignore[return-value]

    def list_items(self, snapshot_id: str) -> List[EvidenceItem]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT i.* FROM evidence_items i
            JOIN evidence_links l ON l.item_id = i.item_id
            WHERE l.snapshot_id = ?
            ORDER BY i.observed_at, i.item_id
            """,
            (snapshot_id,),
        ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def query(self, query: EvidenceQuery = EvidenceQuery()) -> List[EvidenceItem]:
        if query.limit <= 0:
            raise ValueError("evidence query limit must be positive")
        clauses: List[str] = []
        params: List[object] = []
        if query.symbol is not None:
            clauses.append("symbol = ?")
            params.append(query.symbol)
        if query.source_id is not None:
            clauses.append("source_id = ?")
            params.append(query.source_id)
        if query.observed_after is not None:
            clauses.append("observed_at >= ?")
            params.append(query.observed_after)
        if query.text is not None:
            clauses.append("(title LIKE ? OR content LIKE ?)")
            needle = "%" + query.text + "%"
            params.extend([needle, needle])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            "SELECT * FROM evidence_items" + where + " ORDER BY observed_at DESC, item_id LIMIT ?",
            [*params, query.limit],
        ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def list_sources(self) -> List[EvidenceSource]:
        rows = self.connection.execute(
            "SELECT * FROM evidence_sources ORDER BY source_id"
        ).fetchall()
        return [
            EvidenceSource(
                id=row["source_id"],
                name=row["name"],
                kind=row["kind"],
                uri=row["uri"],
                trust_tier=row["trust_tier"],
                metadata=_load(row["metadata_json"]),
            )
            for row in rows
        ]

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()


class InMemoryEvidenceStore:
    """Small Adapter for tests and deterministic local dry runs."""

    def __init__(self) -> None:
        self.sources: Dict[str, EvidenceSource] = {}
        self.items: Dict[str, EvidenceItem] = {}
        self.snapshots: Dict[str, EvidenceSnapshot] = {}
        self.links: List[EvidenceLink] = []
        self.item_symbols: set[tuple[str, str, str]] = set()

    def save_source(self, source: EvidenceSource) -> EvidenceSource:
        self.sources[source.id] = source
        return source

    def save_item(self, item: EvidenceItem) -> EvidenceItem:
        if item.fingerprint:
            for existing in self.items.values():
                if existing.fingerprint == item.fingerprint:
                    return existing
        self.items.setdefault(item.id, item)
        return self.items[item.id]

    def save_snapshot(self, snapshot: EvidenceSnapshot) -> EvidenceSnapshot:
        self.snapshots.setdefault(snapshot.id, snapshot)
        return self.get_snapshot(snapshot.id) or snapshot

    def link(self, link: EvidenceLink) -> EvidenceLink:
        snapshot = self.snapshots.get(link.snapshot_id)
        if snapshot is None:
            raise KeyError("evidence snapshot not found: %s" % link.snapshot_id)
        if snapshot.sealed:
            raise ValueError("evidence snapshot is sealed: %s" % link.snapshot_id)
        if link not in self.links:
            self.links.append(link)
        return link

    def link_symbol(self, snapshot_id: str, item_id: str, symbol: str) -> None:
        symbol = str(symbol or "").strip()
        if not symbol:
            return
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise KeyError("evidence snapshot not found: %s" % snapshot_id)
        if snapshot.sealed:
            raise ValueError("evidence snapshot is sealed: %s" % snapshot_id)
        self.item_symbols.add((snapshot_id, item_id, symbol))

    def list_item_symbols(self, snapshot_id: str, item_id: str) -> List[str]:
        return sorted(
            symbol
            for snap_id, linked_item_id, symbol in self.item_symbols
            if snap_id == snapshot_id and linked_item_id == item_id
        )

    def get_snapshot(self, snapshot_id: str) -> Optional[EvidenceSnapshot]:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            return None
        ids = tuple(sorted({link.item_id for link in self.links if link.snapshot_id == snapshot_id}))
        return EvidenceSnapshot(
            id=snapshot.id,
            captured_at=snapshot.captured_at,
            query=snapshot.query,
            record_ids=ids,
            metadata=snapshot.metadata,
            sealed=snapshot.sealed,
        )

    def seal(self, snapshot_id: str) -> EvidenceSnapshot:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise KeyError("evidence snapshot not found: %s" % snapshot_id)
        sealed = EvidenceSnapshot(
            id=snapshot.id,
            captured_at=snapshot.captured_at,
            query=snapshot.query,
            record_ids=snapshot.record_ids,
            metadata=snapshot.metadata,
            sealed=True,
        )
        self.snapshots[snapshot_id] = sealed
        return self.get_snapshot(snapshot_id)  # type: ignore[return-value]

    def list_items(self, snapshot_id: str) -> List[EvidenceItem]:
        ids = {link.item_id for link in self.links if link.snapshot_id == snapshot_id}
        return sorted(
            [item for item_id, item in self.items.items() if item_id in ids],
            key=lambda item: (item.observed_at, item.id),
        )

    def query(self, query: EvidenceQuery = EvidenceQuery()) -> List[EvidenceItem]:
        if query.limit <= 0:
            raise ValueError("evidence query limit must be positive")
        result: Iterable[EvidenceItem] = self.items.values()
        if query.symbol is not None:
            result = (item for item in result if item.symbol == query.symbol)
        if query.source_id is not None:
            result = (item for item in result if item.source_id == query.source_id)
        if query.observed_after is not None:
            result = (item for item in result if item.observed_at >= query.observed_after)
        if query.text is not None:
            needle = query.text.lower()
            result = (item for item in result if needle in (item.title + " " + item.content).lower())
        return sorted(result, key=lambda item: (item.observed_at, item.id), reverse=True)[: query.limit]

    def list_sources(self) -> List[EvidenceSource]:
        return [self.sources[key] for key in sorted(self.sources)]
