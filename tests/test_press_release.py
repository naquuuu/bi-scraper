# OWNERSHIP: public-derived
"""Press-release listing parser: metadata only, newest first."""

from __future__ import annotations

from datetime import date

from bi_scraper.parsers.press_release import parse_press_release_listing


def test_listing_returns_dated_metadata_newest_first(fixture_text):
    html = fixture_text("press_release_list.html")
    metas = parse_press_release_listing(
        html, base_url="https://www.bi.go.id/id/publikasi/ruang-media/news-release/"
    )
    assert len(metas) == 3
    assert [meta.date for meta in metas] == [
        date(2026, 8, 19),
        date(2026, 7, 22),
        date(2026, 6, 9),
    ]
    assert metas[0].url == (
        "https://www.bi.go.id/id/publikasi/ruang-media/news-release/Pages/sp_2816226.aspx"
    )
    assert metas[0].doc_type == "page"
    assert metas[-1].doc_type == "pdf"
    assert metas[0].title == "BI-Rate Tetap 5,75 Persen"


def test_listing_ignores_navigation_links():
    html = """
    <ul class="nav"><li><a href="/id/publikasi/Default.aspx">Publikasi</a></li></ul>
    """
    metas = parse_press_release_listing(html)
    assert metas == []


def test_report_listing_box_list_markup(fixture_text):
    """New markup (report listings): empty box-list anchors inside media cards."""

    metas = parse_press_release_listing(
        fixture_text("report_list.html"),
        base_url="https://www.bi.go.id/id/publikasi/laporan/default.aspx",
    )
    assert len(metas) == 3
    first = metas[0]
    assert first.date == date(2026, 9, 14)
    assert first.title == "Laporan Kelembagaan Bank Indonesia Triwulan II - 2026"
    assert first.doc_type == "page"
    assert first.url == (
        "https://www.bi.go.id/id/publikasi/laporan/Pages/LKBI-Tw.II-2026.aspx"
    )
    assert metas[1].date == date(2026, 8, 21)
    assert metas[1].url.startswith("https://www.bi.go.id/id/publikasi/kajian/Pages/")
    assert metas[2].date is None
    assert metas[2].title == "Kajian Stabilitas Keuangan (bulanan berjalan)"


def test_report_listing_excludes_filter_links():
    html = """
    <div class="media"><a href="/id/publikasi/laporan/default.aspx?Kategori=x&amp;Periode="
        class="box-list__hyperlink"></a></div>
    """
    assert parse_press_release_listing(html) == []
