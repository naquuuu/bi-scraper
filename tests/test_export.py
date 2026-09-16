# OWNERSHIP: tooling
"""Export contracts: study-pack headers, thin warnings, no verbatim content."""

from __future__ import annotations

from bi_scraper.chapter_map import get_chapter
from bi_scraper.export import export_notebook, export_portfolio


def test_notebook_header_flags_and_my_notes(store, settings):
    store.add_document(
        chapter=2,
        url="https://www.bi.go.id/id/publikasi/x",
        title="Doc A",
        content="page text",
        doc_date="2026-09-16",
    )
    store.add_document(
        chapter=2,
        url="inbox://n.md",
        title="My note",
        content="Ringkasan saya",
        source_type="my-notes",
        doc_kind="note",
        doc_date="2026-09-12",
    )
    store.set_fetch_log(2, "incremental")

    path = export_notebook(store, get_chapter(2), settings)
    text = path.read_text(encoding="utf-8")
    assert "Fetched-At:" in text
    assert "Chapter newest dated public doc: 2026-09-16" in text
    assert "[NEWER-THAN-SYLLABUS]" in text  # ch2 syllabus pin: 2026-07-18
    assert "Ringkasan saya" in text
    assert "https://www.bi.go.id/id/publikasi/x" in text


def test_notebook_includes_full_table_and_text(store, settings):
    store.add_document(
        chapter=2,
        url="https://www.bi.go.id/x/1",
        title="Doc one",
        content="Fakta lengkap satu.",
        doc_date="2026-09-16",
    )
    store.add_document(
        chapter=2,
        url="https://www.bi.go.id/x/2",
        title="Doc two",
        content="Doc two",
        doc_date="2026-09-15",
    )
    store.add_indicator(
        chapter=2, name="BI-Rate", period="2026-08-19", value=5.75, unit="%", url="u1"
    )
    store.add_indicator(
        chapter=2, name="BI-Rate", period="2026-07-22", value=5.75, unit="%", url="u2"
    )
    store.add_indicator(
        chapter=2, name="BI-Rate", period="2026-06-18", value=5.75, unit="%", url="u3"
    )
    path = export_notebook(store, get_chapter(2), settings)
    text = path.read_text(encoding="utf-8")
    assert "## Tabel angka lengkap" in text
    for period in ("2026-08-19", "2026-07-22", "2026-06-18"):
        assert f"| {period} | BI-Rate |" in text
    assert "## Isi Sumber (full text)" in text
    assert "Fakta lengkap satu." in text
    assert "_(konten belum di-scrape; metadata saja)_" in text


def test_fallback_only_chapter_reports_honest_unknown(store, settings):
    store.add_document(
        chapter=5,
        url="https://www.bi.go.id/id/fungsi-utama/sistem-pembayaran/page",
        title="Page doc",
        content="page text",
    )
    path = export_notebook(store, get_chapter(5), settings)
    text = path.read_text(encoding="utf-8")
    assert "HONEST-UNKNOWN" in text
    assert "[NEWER-THAN-SYLLABUS]" not in text
    assert "freshness unknown" in text


def test_portfolio_excludes_verbatim_and_renders_chart(store, settings):
    store.add_document(
        chapter=2,
        url="https://www.bi.go.id/id/publikasi/x",
        title="Doc A",
        content="VERBATIM-COURSE-TEXT",
        doc_date="2026-09-16",
    )
    store.add_indicator(
        chapter=2, name="BI-Rate", period="2026-07-22", value=5.75, unit="%", url="u1"
    )
    store.add_indicator(
        chapter=2, name="BI-Rate", period="2026-08-19", value=5.75, unit="%", url="u2"
    )

    path = export_portfolio(store, get_chapter(2), settings)
    text = path.read_text(encoding="utf-8")
    assert "VERBATIM-COURSE-TEXT" not in text
    assert "Public-data-only export" in text
    assert (settings.exports_dir / "portfolio" / "ch2_bi-rate.png").is_file()
    assert "![BI-Rate](ch2_bi-rate.png)" in text
    assert "## My analysis" in text


def test_chapter7_thin_warning(store, settings):
    path = export_notebook(store, get_chapter(7), settings)
    text = path.read_text(encoding="utf-8")
    assert "thin coverage expected" in text
    assert "no public documents stored yet" in text


def test_portfolio_empty_store_is_honest(store, settings):
    path = export_portfolio(store, get_chapter(7), settings)
    text = path.read_text(encoding="utf-8")
    assert "No chartable indicator series stored yet" in text
    assert "No indicator rows stored yet" in text
