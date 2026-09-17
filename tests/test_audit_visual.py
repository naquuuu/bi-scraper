# OWNERSHIP: tooling
"""Offline audit-visuals tests (saved snapshots only, zero network)."""

from __future__ import annotations

from bi_scraper.chapter_map import get_chapter
from bi_scraper.cli import run_audit_visuals

HEAVY_HTML = """
<html><body>
<img src="/id/x/a.jpg" />
<img src="/id/x/b.jpg" />
<img src="/id/x/c.jpg" />
</body></html>
"""

LIGHT_HTML = """
<html><body><p>Teks panjang tanpa gambar.</p>
<img src="/SiteAssets/logo-bi.png" />
</body></html>
"""


def test_audit_flags_image_heavy_snapshot(store, tmp_path):
    heavy = tmp_path / "heavy.html"
    heavy.write_text(HEAVY_HTML, encoding="utf-8")
    light = tmp_path / "light.html"
    light.write_text(LIGHT_HTML, encoding="utf-8")

    store.add_document(
        chapter=1,
        url="https://www.bi.go.id/id/x/heavy",
        title="Heavy page",
        content="pendek",
        doc_kind="web_page",
        raw_path=str(heavy),
    )
    store.add_document(
        chapter=1,
        url="https://www.bi.go.id/id/x/light",
        title="Light page",
        content="teks yang cukup panjang " * 100,
        doc_kind="web_page",
        raw_path=str(light),
    )

    summaries = run_audit_visuals(store=store, chapters=[get_chapter(1)])
    assert summaries[0].scanned == 2
    assert summaries[0].flagged == 1

    flagged = store.visual_heavy_documents(1)
    assert len(flagged) == 1
    assert flagged[0]["url"] == "https://www.bi.go.id/id/x/heavy"
    assert flagged[0]["image_count"] == 3


def test_audit_ignores_unscraped_metadata_docs(store, tmp_path):
    raw = tmp_path / "listing.html"
    raw.write_text(HEAVY_HTML, encoding="utf-8")
    store.add_document(
        chapter=3,
        url="https://www.bi.go.id/id/publikasi/x",
        title="Demo Release",
        content="Demo Release",  # content == title -> not audited
        doc_kind="press_release_page",
        raw_path=str(raw),
    )
    summaries = run_audit_visuals(store=store, chapters=[get_chapter(3)])
    assert summaries[0].scanned == 0
    assert summaries[0].flagged == 0


def test_audit_frequency_filters_shared_site_chrome(store, tmp_path):
    chrome = (
        '<img src="/SiteAssets/promo-a.jpg" />'
        '<img src="/SiteAssets/promo-b.jpg" />'
        '<img src="/SiteAssets/promo-c.jpg" />'
    )
    long_text = "teks panjang " * 200
    for index in range(10):
        path = tmp_path / f"chrome_{index}.html"
        path.write_text(
            f"<html><body><p>{long_text}</p>{chrome}</body></html>", encoding="utf-8"
        )
        store.add_document(
            chapter=1,
            url=f"https://www.bi.go.id/id/chrome/{index}",
            title=f"Chrome {index}",
            content=long_text,
            doc_kind="web_page",
            raw_path=str(path),
        )

    heavy = tmp_path / "heavy.html"
    heavy.write_text(HEAVY_HTML, encoding="utf-8")
    store.add_document(
        chapter=1,
        url="https://www.bi.go.id/id/x/heavy",
        title="Heavy page",
        content="pendek",
        doc_kind="web_page",
        raw_path=str(heavy),
    )

    summaries = run_audit_visuals(store=store, chapters=[get_chapter(1)])
    assert summaries[0].scanned == 11
    assert summaries[0].flagged == 1  # only the unique-image page
    flagged = store.visual_heavy_documents(1)
    assert len(flagged) == 1
    assert flagged[0]["url"] == "https://www.bi.go.id/id/x/heavy"
    assert flagged[0]["image_count"] == 3
