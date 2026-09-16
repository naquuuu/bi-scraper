# OWNERSHIP: tooling
"""SQLite storage + FTS5 behavior."""

from __future__ import annotations

from bi_scraper.storage.sqlite_store import StudyStore


def test_add_search_and_snippet(store):
    inserted = store.add_document(
        chapter=2,
        url="https://www.bi.go.id/id/statistik/indikator/inflasi.aspx",
        title="Inflasi dan Nilai Tukar",
        content="Dalam laporan ini inflasi bulanan dibahas bersama nilai tukar.",
        doc_date="2026-09-16",
    )
    assert inserted is True
    rows = store.search("inflasi")
    assert len(rows) == 1
    assert "[" in rows[0]["snippet"]
    assert rows[0]["chapter"] == 2


def test_idempotent_document_insert(store):
    kwargs = dict(
        chapter=1,
        url="https://www.bi.go.id/id/tentang-bi/profil/Default.aspx",
        title="Profil BI",
        content="Profil Bank Indonesia.",
        doc_date="2026-09-16",
    )
    assert store.add_document(**kwargs) is True
    assert store.add_document(**kwargs) is False


def test_documents_newest_first(store):
    store.add_document(chapter=1, url="https://a", title="old", content="x", doc_date="2026-01-01")
    store.add_document(chapter=1, url="https://b", title="new", content="y", doc_date="2026-09-01")
    store.add_document(chapter=1, url="https://c", title="undated", content="z")
    rows = store.documents_for_chapter(1)
    assert [row["doc_date"] for row in rows] == ["2026-09-01", "2026-01-01", None]


def test_newest_public_date_ignores_my_notes(store):
    store.add_document(chapter=2, url="https://a", title="public", doc_date="2026-08-01")
    store.add_document(
        chapter=2,
        url="inbox://n.md",
        title="note",
        content="my note",
        source_type="my-notes",
        doc_kind="note",
        doc_date="2026-09-16",
    )
    assert store.newest_public_date(2).isoformat() == "2026-08-01"


def test_indicator_insert_is_idempotent(store):
    kwargs = dict(
        chapter=2, name="BI-Rate", period="2026-08-19", value=5.75, unit="%", url="https://x"
    )
    assert store.add_indicator(**kwargs) is True
    assert store.add_indicator(**kwargs) is False
    series = store.indicator_series(2, "BI-Rate")
    assert len(series) == 1
    assert series[0]["value"] == 5.75


def test_rebuild_fts_keeps_search_working(store):
    store.add_document(chapter=3, url="https://x", title="Moneter", content="kebijakan moneter")
    store.rebuild_fts()
    assert len(store.search("moneter")) == 1


def test_count_documents(store):
    assert store.count_documents() == 0
    store.add_document(chapter=1, url="https://x", title="t", content="c")
    assert store.count_documents() == 1


def test_date_source_derivation_and_real_date_exclusion(store):
    store.add_document(chapter=2, url="https://dated", title="dated", doc_date="2026-08-19")
    store.add_document(chapter=2, url="https://undated", title="undated")
    rows = {row["url"]: row for row in store.documents_for_chapter(2)}
    assert rows["https://dated"]["date_source"] == "parsed"
    assert rows["https://undated"]["date_source"] == "fetch_fallback"
    assert store.newest_real_date(2).isoformat() == "2026-08-19"
    assert store.fallback_doc_count(2) == 1


def test_newest_real_date_none_when_only_fallback(store):
    store.add_document(chapter=5, url="https://page", title="page doc")
    assert store.newest_real_date(5) is None
    assert store.fallback_doc_count(5) == 1


def test_migration_backfills_date_source_on_legacy_db(tmp_path):
    import sqlite3

    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            doc_date TEXT,
            fetched_at TEXT NOT NULL,
            source_type TEXT NOT NULL,
            doc_kind TEXT NOT NULL,
            raw_path TEXT,
            content TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            UNIQUE (chapter, url, content_hash)
        );
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            title, content, content='documents', content_rowid='id',
            tokenize='unicode61'
        );
        CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END;
        CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO documents_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        """
    )
    # Simulate a row written through the old add_document: FTS index in sync.
    conn.execute(
        "INSERT INTO documents (chapter, url, title, doc_date, fetched_at, "
        "source_type, doc_kind, content, content_hash) "
        "VALUES (5, 'https://legacy', 'page', NULL, '2026-01-01T00:00:00Z', "
        "'public', 'web_page', '', 'h1')"
    )
    rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO documents_fts(rowid, title, content) VALUES (?, 'page', '')",
        (rowid,),
    )
    conn.commit()
    conn.close()

    store = StudyStore(legacy)
    try:
        row = store.conn.execute(
            "SELECT date_source FROM documents WHERE url = 'https://legacy'"
        ).fetchone()
        assert row["date_source"] == "fetch_fallback"
        assert store.newest_real_date(5) is None
        assert len(store.search("page")) == 1  # FTS stays consistent after migration
    finally:
        store.close()
