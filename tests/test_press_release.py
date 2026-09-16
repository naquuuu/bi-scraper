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
