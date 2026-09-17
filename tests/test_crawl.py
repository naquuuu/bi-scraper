# OWNERSHIP: tooling
"""Offline hub-crawl tests: depth limits, PDF discovery, idempotency."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import httpx

from bi_scraper.chapter_map import get_chapter
from bi_scraper.cli import FetchSummary, _fetch_hub
from bi_scraper.http_client import AllowAllRobots, PoliteClient
from bi_scraper.sources import KIND_HUB, Source

FIXTURES = Path(__file__).parent / "fixtures"

ROOT = "https://www.bi.go.id/id/rupiah/Default.aspx"
CHILD = "https://www.bi.go.id/id/rupiah/gambar-uang/Default.aspx"
GRAND = "https://www.bi.go.id/id/rupiah/gambar-uang/detail/uang.aspx"
DEEP = "https://www.bi.go.id/id/rupiah/gambar-uang/detail/tahun/2026.aspx"
PDF = "https://www.bi.go.id/id/rupiah/gambar-uang/Documents/brosur.pdf"

ROOT_HTML = f"""
<html><body><h1 id="pageTitle">Rupiah</h1><p>Hub rupiah.</p>
<a href="{CHILD}">Gambar Uang</a>
<a href="{PDF}">Brosur</a>
<a href="/id/rupiah/asset.css">css</a>
<a href="/id/layanan/x">outside</a>
</body></html>
"""

CHILD_HTML = f"""
<html><body><h1 id="pageTitle">Gambar Uang</h1><p>Gambar uang.</p>
<a href="{GRAND}">Detail</a>
</body></html>
"""

GRAND_HTML = f"""
<html><body><h1 id="pageTitle">Detail Uang</h1><p>Detail.</p>
<a href="{DEEP}">Tahun</a>
</body></html>
"""


def _offline_client(settings, handler) -> PoliteClient:
    return PoliteClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
        sleep=lambda seconds: None,
        robots_gate=AllowAllRobots(),
    )


def _summary() -> FetchSummary:
    return FetchSummary(
        chapter=6, name="Rupiah (hub)", mode="incremental", start="2026-09-01", end="2026-09-17"
    )


def test_hub_crawl_depth_limits_and_pdf_discovery(store, settings):
    settings = dataclasses.replace(settings, hub_max_pages=10)
    pdf_bytes = (FIXTURES / "sample.pdf").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.lower().endswith(".pdf"):
            return httpx.Response(200, content=pdf_bytes)
        if url == ROOT:
            return httpx.Response(200, text=ROOT_HTML)
        if url == CHILD:
            return httpx.Response(200, text=CHILD_HTML)
        if url == GRAND:
            return httpx.Response(200, text=GRAND_HTML)
        return httpx.Response(
            200, text="<html><body><h1 id='pageTitle'>Deep</h1><p>Deep</p></body></html>"
        )

    source = Source(
        6, "Rupiah (hub)", ROOT, KIND_HUB, hub_prefix="/id/rupiah/", max_depth=2
    )
    _fetch_hub(
        store=store,
        settings=settings,
        client=_offline_client(settings, handler),
        source=source,
        chapter=get_chapter(6),
        summary=_summary(),
    )
    urls = {row["url"] for row in store.documents_for_chapter(6, source_type="public")}
    assert ROOT in urls
    assert CHILD in urls
    assert GRAND in urls  # depth 2 included
    assert DEEP not in urls  # depth 3 excluded by max_depth
    assert PDF in urls  # PDF discovered on the hub root
    pdf_rows = [r for r in store.documents_for_chapter(6) if r["url"] == PDF]
    assert "Hello BI Scraper PDF" in pdf_rows[0]["content"]


def test_hub_crawl_is_idempotent(store, settings):
    settings = dataclasses.replace(settings, hub_max_pages=2)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == ROOT:
            return httpx.Response(200, text=ROOT_HTML)
        return httpx.Response(200, text=CHILD_HTML)

    source = Source(
        6, "Rupiah (hub)", ROOT, KIND_HUB, hub_prefix="/id/rupiah/", max_depth=1
    )
    _fetch_hub(
        store=store,
        settings=settings,
        client=_offline_client(settings, handler),
        source=source,
        chapter=get_chapter(6),
        summary=_summary(),
    )
    second = _summary()
    _fetch_hub(
        store=store,
        settings=settings,
        client=_offline_client(settings, handler),
        source=source,
        chapter=get_chapter(6),
        summary=second,
    )
    assert second.fetched == 0  # nothing new on the second run
    assert store.doc_count(6, source_type="public") == 2  # root + child only (cap 2)


def test_hub_crawl_respects_page_cap(store, settings):
    settings = dataclasses.replace(settings, hub_max_pages=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ROOT_HTML)

    source = Source(
        6, "Rupiah (hub)", ROOT, KIND_HUB, hub_prefix="/id/rupiah/", max_depth=2
    )
    _fetch_hub(
        store=store,
        settings=settings,
        client=_offline_client(settings, handler),
        source=source,
        chapter=get_chapter(6),
        summary=_summary(),
    )
    assert store.doc_count(6, source_type="public") == 1  # only the hub root
