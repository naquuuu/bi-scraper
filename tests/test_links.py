# OWNERSHIP: public-derived
"""Hub crawl link extraction: prefix scoping and asset/query exclusion."""

from __future__ import annotations

from bi_scraper.parsers.links import extract_internal_links, is_crawlable

PREFIX = "/id/tentang-bi/"
BASE = "https://www.bi.go.id/id/tentang-bi/Default.aspx"


def test_extracts_only_in_section_links():
    html = """
    <a href="/id/tentang-bi/profil/Default.aspx">Profil</a>
    <a href="/id/tentang-bi/sejarah-bi/Default.aspx#top">Sejarah</a>
    <a href="/id/rupiah/Default.aspx">Rupiah</a>
    <a href="/id/tentang-bi/Default.aspx?x=1">Filter</a>
    <a href="/Style Library/biweb/x.css">css</a>
    <a href="/id/tentang-bi/img/logo.png">img</a>
    <a href="/id/tentang-bi/asset.css">css in section</a>
    <a href="https://example.com/id/tentang-bi/x">external</a>
    <a href="mailto:bicara@bi.go.id">mail</a>
    <a href="/id/tentang-bi/profil/Default.aspx">Profil (dupe)</a>
    """
    links = extract_internal_links(html, BASE, PREFIX)
    assert links == [
        "https://www.bi.go.id/id/tentang-bi/profil/Default.aspx",
        "https://www.bi.go.id/id/tentang-bi/sejarah-bi/Default.aspx",
    ]


def test_is_crawlable_rules():
    base = "https://www.bi.go.id"
    assert is_crawlable(base + "/id/rupiah/gambar-uang/Default.aspx", "/id/rupiah/")
    assert is_crawlable(base + "/id/rupiah/Documents/brosur.pdf", "/id/rupiah/")
    assert not is_crawlable(base + "/id/layanan/museum-bi/x", "/id/rupiah/")
    assert not is_crawlable(base + "/id/rupiah/Default.aspx?Kategori=x", "/id/rupiah/")
    assert not is_crawlable(base + "/id/rupiah/x.png", "/id/rupiah/")
    assert not is_crawlable("https://example.com/id/rupiah/x", "/id/rupiah/")
    assert not is_crawlable(base + "/id/archive/default.aspx", "/id/archive/")
