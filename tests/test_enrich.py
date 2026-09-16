# OWNERSHIP: tooling
"""Offline enrichment tests: HTML + public PDF text, idempotency, no live hits."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
from pypdf import PdfWriter

from bi_scraper.chapter_map import get_chapter
from bi_scraper.cli import run_enrich
from bi_scraper.http_client import AllowAllRobots, PoliteClient

FIXTURES = Path(__file__).parent / "fixtures"


def _client(settings, handler) -> PoliteClient:
    return PoliteClient(
        settings=settings,
        transport=httpx.MockTransport(handler),
        sleep=lambda seconds: None,
        robots_gate=AllowAllRobots(),
    )


def test_enrich_html_and_pdf_then_idempotent(store, settings, fixture_text):
    page_url = "https://www.bi.go.id/id/publikasi/ruang-media/news-release/Pages/sp_demo.aspx"
    pdf_url = "https://www.bi.go.id/id/publikasi/laporan/Documents/demo.pdf"
    store.add_document(
        chapter=3,
        url=page_url,
        title="Demo Release",
        content="Demo Release",
        doc_kind="press_release_page",
        doc_date="2026-09-01",
    )
    store.add_document(
        chapter=3,
        url=pdf_url,
        title="Demo Report",
        content="Demo Report",
        doc_kind="press_release_pdf",
        doc_date="2026-09-02",
    )
    page_html = fixture_text("sample_page.html")
    pdf_bytes = (FIXTURES / "sample.pdf").read_bytes()
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if request.url.path.lower().endswith(".pdf"):
            return httpx.Response(
                200, content=pdf_bytes, headers={"Content-Type": "application/pdf"}
            )
        return httpx.Response(200, text=page_html)

    summaries = run_enrich(
        store=store,
        settings=settings,
        chapters=[get_chapter(3)],
        client=_client(settings, handler),
    )
    assert summaries[0].updated == 2
    assert summaries[0].failures == []
    assert calls["count"] == 2

    rows = {row["url"]: row for row in store.documents_for_chapter(3, source_type="public")}
    assert "Informasi inflasi" in rows[page_url]["content"]
    assert "Hello BI Scraper PDF" in rows[pdf_url]["content"]
    assert rows[page_url]["raw_path"] is not None

    # Second run: nothing pending, no HTTP requests.
    def forbidden(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no HTTP request expected on a second enrich run")

    second = run_enrich(
        store=store,
        settings=settings,
        chapters=[get_chapter(3)],
        client=_client(settings, forbidden),
    )
    assert second[0].pending == 0
    assert second[0].updated == 0


def test_enrich_reports_encrypted_pdf_and_continues(store, settings):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    secure_bytes = buffer.getvalue()

    store.add_document(
        chapter=4,
        url="https://www.bi.go.id/id/publikasi/laporan/Documents/secure.pdf",
        title="Secure Report",
        content="Secure Report",
        doc_kind="press_release_pdf",
        doc_date="2026-09-01",
    )
    store.add_document(
        chapter=4,
        url="https://www.bi.go.id/id/publikasi/laporan/Documents/open.pdf",
        title="Open Report",
        content="Open Report",
        doc_kind="press_release_pdf",
        doc_date="2026-09-02",
    )
    open_bytes = (FIXTURES / "sample.pdf").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if "secure" in request.url.path:
            return httpx.Response(200, content=secure_bytes)
        return httpx.Response(200, content=open_bytes)

    summaries = run_enrich(
        store=store,
        settings=settings,
        chapters=[get_chapter(4)],
        client=_client(settings, handler),
    )
    assert summaries[0].updated == 1
    assert len(summaries[0].failures) == 1
    assert "encrypted" in summaries[0].failures[0]
    rows = {row["url"]: row for row in store.documents_for_chapter(4, source_type="public")}
    assert "Hello BI Scraper PDF" in rows[
        "https://www.bi.go.id/id/publikasi/laporan/Documents/open.pdf"
    ]["content"]
