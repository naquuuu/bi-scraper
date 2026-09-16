# OWNERSHIP: tooling
"""SQLite storage + FTS5 behavior."""

from __future__ import annotations


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
